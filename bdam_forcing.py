"""Nonnegative C1-periodic climatologies and conservative circular transport.

Only NumPy is required. Times are elapsed water-year days; day zero is October 1.
MF6 receives interval means, rather than samples of these continuous curves.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

YEAR = 365.0
VERSION = "periodic-cubic-circular-transport-v1"
MONTH_DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
WATER_YEAR_OFFSET = int(sum(MONTH_DAYS[:9]))


class PeriodicCurve:
    """Cyclic shape-preserving Hermite interpolation of 365 daily centers.

    Cyclic harmonic-mean slopes give C1 closure and avoid negative overshoot.
    A positive uniform normalization preserves the sum of the source daily rates.
    The primitive is exact for this piecewise cubic, including wrapped intervals.
    """

    def __init__(self, daily):
        y = np.asarray(daily, dtype=float)
        if y.shape != (365,) or not np.all(np.isfinite(y)) or np.any(y < 0):
            raise ValueError("A climatology must have 365 finite nonnegative rates.")
        delta = np.roll(y, -1) - y
        left = np.roll(delta, 1)
        slopes = np.zeros(365)
        mask = left * delta > 0
        slopes[mask] = 2 * left[mask] * delta[mask] / (left[mask] + delta[mask])
        nxt, ms = np.roll(y, -1), np.roll(slopes, -1)
        self.coeff = np.stack((y, slopes, 3*(nxt-y)-2*slopes-ms,
                               2*(y-nxt)+slopes+ms), axis=1)
        integrals = self.coeff @ np.array([1., .5, 1/3, .25])
        factor = y.sum() / integrals.sum() if y.sum() else 1.
        self.coeff *= factor
        self.cumulative = np.r_[0., np.cumsum(integrals * factor)]
        self.total = float(self.cumulative[-1])
        self.floor = float(y.min() * factor)
        self.peak = float(np.argmax(y) + .5)

    def value(self, time, derivative=False):
        phase = np.mod(np.asarray(time, dtype=float) - .5, YEAR)
        index = np.floor(phase).astype(int)
        u = phase-index
        c = self.coeff[index]
        if derivative:
            return c[..., 1] + 2*c[..., 2]*u + 3*c[..., 3]*u*u
        return c[..., 0] + u*(c[..., 1]+u*(c[..., 2]+u*c[..., 3]))

    def primitive(self, time):
        phase = np.asarray(time, dtype=float) - .5
        cycles = np.floor(phase / YEAR)
        remainder = np.mod(phase, YEAR)
        index = np.minimum(np.floor(remainder).astype(int), 364)
        u = remainder-index
        c = self.coeff[index]
        return (cycles*self.total + self.cumulative[index]
                + u*(c[..., 0]+u*(c[..., 1]/2+u*(c[..., 2]/3+u*c[..., 3]/4))))

    def integral(self, start, end):
        return self.primitive(end)-self.primitive(start)


class TransformedCurve:
    def __init__(self, source, magnitude_scale=1., shift_days=0., width_factor=1., center_day=None):
        self.source = source
        self.scale, self.shift, self.width = map(float, (magnitude_scale, shift_days, width_factor))
        self.center = source.peak if center_day is None or np.asarray(center_day).size == 0 else float(center_day) % YEAR
        if (not np.all(np.isfinite([self.scale, self.shift, self.width, self.center]))
                or self.scale < 0 or self.width <= 0):
            raise ValueError("Forcing controls must be finite, with magnitude >= 0 and width > 0.")

    def inverse(self, time):
        relative = np.asarray(time, dtype=float)-self.shift-self.center
        cycle = np.floor((relative + YEAR/2)/YEAR)
        theta = (relative-cycle*YEAR)*2*np.pi/YEAR
        angle = 2*np.arctan2(np.sin(theta/2)/self.width, np.cos(theta/2))
        return self.center + cycle*YEAR + angle*YEAR/(2*np.pi)

    def value(self, time):
        source_time = self.inverse(time)
        theta = (source_time-self.center)*2*np.pi/YEAR
        jacobian = self.width / (np.cos(theta/2)**2 + self.width**2*np.sin(theta/2)**2)
        return self.scale*(self.source.floor +
                           (self.source.value(source_time)-self.source.floor)/jacobian)

    def integral(self, start, end):
        a, b = self.inverse(start), self.inverse(end)
        excess = self.source.integral(a, b)-self.source.floor*(b-a)
        return self.scale*(self.source.floor*(np.asarray(end)-np.asarray(start))+excess)

    def means(self, edges):
        edges = np.asarray(edges, dtype=float)
        return self.integral(edges[:-1], edges[1:])/np.diff(edges)

    def diagnostics(self):
        # Circular RMS distance about the shifted anchor, not ordinary date variance.
        t = (np.arange(365*8)+.5)/8
        excess = np.maximum(self.value(t)-self.scale*self.source.floor, 0.)
        distance = (t-self.center-self.shift+YEAR/2) % YEAR-YEAR/2
        rms = float(np.sqrt(np.dot(excess, distance**2)/excess.sum())) if excess.sum() else 0.
        return dict(annual_integral=float(self.integral(0., YEAR)),
                    background_rate=self.scale*self.source.floor,
                    center_day=self.center, shift_days=self.shift,
                    width_factor=self.width, magnitude_scale=self.scale,
                    seasonal_rms_days=rms)


def _calendar_daily(monthly):
    return np.repeat(np.asarray(monthly, dtype=float), MONTH_DAYS)


def _weighted_integrals(curve, edges, calendar_factors):
    # Recharge efficiency remains tied to calendar months; split at every month edge.
    boundaries = np.mod(np.r_[0, np.cumsum(MONTH_DAYS)]-WATER_YEAR_OFFSET, YEAR)
    cuts = np.unique(np.r_[edges, boundaries, 0., YEAR])
    centers = (cuts[:-1]+cuts[1:])/2
    month = np.searchsorted(np.cumsum(MONTH_DAYS), (centers+WATER_YEAR_OFFSET) % YEAR, side="right")
    volumes = curve.integral(cuts[:-1], cuts[1:])*np.asarray(calendar_factors)[month]
    prefix = np.r_[0., np.cumsum(volumes)]
    return np.diff(prefix[np.searchsorted(cuts, edges)])/np.diff(edges)


def generate(config, edges):
    """Return five MF6 interval rates plus baseline inflow and review diagnostics."""
    edges = np.asarray(edges, dtype=float)
    if edges[0] != 0 or not np.isclose(edges[-1], YEAR) or np.any(np.diff(edges) <= 0):
        raise ValueError("Forcing edges must partition exactly one 365-day year.")
    root = Path(config.get("source_root", Path(__file__).resolve().parent))
    hydro = np.genfromtxt(root/config["usgs_hydrograph_file"], delimiter=",", names=True)
    if (hydro.shape != (365,) or not np.array_equal(hydro["day_of_year"], np.arange(1, 366))
            or np.any(~np.isfinite(hydro["normalized_flow_factor"]))
            or np.any(hydro["normalized_flow_factor"] <= 0)):
        raise ValueError("Hydrograph must contain 365 positive day/factor rows.")
    qfactor = hydro["normalized_flow_factor"]
    qfactor = qfactor/qfactor.mean()
    et = np.asarray(config["synthetic_land_et_monthly_factor"], dtype=float).ravel()
    et = et/np.average(et, weights=MONTH_DAYS)
    ppt = np.asarray(config["pullman_monthly_precipitation_mm"], dtype=float).ravel()/1000/MONTH_DAYS
    daily = dict(inflow=config["synthetic_mean_streamflow_m3_per_day"]*qfactor,
                 et=config["synthetic_mean_land_et_m_per_day"]*_calendar_daily(et),
                 precipitation=_calendar_daily(ppt))
    daily = {k: np.roll(v, -WATER_YEAR_OFFSET) for k, v in daily.items()}
    controls = config["forcing_controls"]
    curves = {k: TransformedCurve(PeriodicCurve(v), **controls[k]) for k, v in daily.items()}
    efficiency = (config["synthetic_recharge_fraction_of_precipitation"]*
                  np.asarray(config["synthetic_recharge_monthly_factor"], dtype=float).ravel())
    rates = dict(upstream_inflow_m3_per_day=curves["inflow"].means(edges),
                 land_et_m_per_day=curves["et"].means(edges),
                 lake_precipitation_m_per_day=curves["precipitation"].means(edges),
                 land_recharge_m_per_day=_weighted_integrals(curves["precipitation"], edges, efficiency),
                 lake_evaporation_m_per_day=curves["et"].means(edges)*
                     config["synthetic_lake_evaporation_fraction_of_land_et"])
    reference_mean = config.get("reference_mean_streamflow_m3_per_day", config["synthetic_mean_streamflow_m3_per_day"])
    reference = PeriodicCurve(np.roll(reference_mean*qfactor, -WATER_YEAR_OFFSET))
    reference_rates = reference.integral(edges[:-1], edges[1:])/np.diff(edges)
    month_edges = np.r_[0., np.cumsum([31,30,31,31,28,31,30,31,30,31,31,30])]
    week_edges = np.linspace(0., YEAR, 53)
    def calendar_rates(calendar_edges):
        output = dict(upstream_inflow_m3_per_day=curves["inflow"].means(calendar_edges),
                      land_et_m_per_day=curves["et"].means(calendar_edges),
                      lake_precipitation_m_per_day=curves["precipitation"].means(calendar_edges),
                      land_recharge_m_per_day=_weighted_integrals(curves["precipitation"], calendar_edges, efficiency),
                      lake_evaporation_m_per_day=curves["et"].means(calendar_edges)*config["synthetic_lake_evaporation_fraction_of_land_et"])
        return {name: np.r_[v,v[-1]].tolist() for name,v in output.items()}
    review_time = np.arange(365*4)/4
    return dict(version=VERSION, rates={k: np.r_[v, v[-1]].tolist() for k, v in rates.items()},
                reference_inflow=np.r_[reference_rates, reference_rates[-1]].tolist(),
                monthly_rates=calendar_rates(month_edges), weekly_rates=calendar_rates(week_edges),
                diagnostics={**{k: v.diagnostics() for k, v in curves.items()},
                    "annual_land_infiltration_m": float(np.dot(rates["land_recharge_m_per_day"], np.diff(edges)))},
                review=dict(time_days=review_time.tolist(),
                            **{k: v.value(review_time).tolist() for k, v in curves.items()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    args.output.write_text(json.dumps(generate(request["config"], request["edges"]), indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    main()

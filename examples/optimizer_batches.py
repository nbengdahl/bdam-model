"""Driver boundary example: supply your optimizer and objective externally."""
from bdam import Study


def evaluate_candidates(study_root, candidates, iteration):
    study = Study(study_root)
    rows = [{"case_id":f"particle-{i}","parameters":candidate,
             "metadata":{"iteration":iteration}} for i,candidate in enumerate(candidates)]
    batch = f"iteration-{iteration}"
    study.submit(rows,batch)
    return study.evaluate(batch)  # Caller reads summaries and computes objectives.

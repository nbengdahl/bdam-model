classdef applyBDamConductivityTest < matlab.unittest.TestCase
    methods (TestClassSetup)
        function sourcePath(t)
            t.applyFixture(matlab.unittest.fixtures.PathFixture(fileparts(fileparts(mfilename('fullpath')))));
        end
    end
    methods (Test)
        function midpointAndDepth(t)
            kb=.03*ones(7,9,5); vb=.003*ones(size(kb));
            channel=false(7,9);channel(4,5)=true;
            [k,v,z]=applyBDamConductivity(kb,vb,channel,zeros(7,9),1,1,t.settings(1));
            t.verifyEqual(nnz(z.core_footprint),1);t.verifyEqual(nnz(z.halo_footprint),8);
            t.verifyEqual(k(z.core_mask),ones(3,1));
            t.verifyEqual(v(z.core_mask),k(z.core_mask));
            t.verifyEqual(k(z.halo_mask),.515*ones(24,1),AbsTol=1e-15);
            t.verifyEqual(v(z.halo_mask),.5015*ones(24,1),AbsTol=1e-15);
            t.verifyFalse(any(z.mask(:,:,1:2),'all'));
            t.verifyEqual(k(~z.mask),kb(~z.mask));t.verifyEqual(v(~z.mask),vb(~z.mask));
        end
        function irregularPlacementAndClipping(t)
            for offset=0:3
                channel=false(8,11);channel(1+offset,1+offset)=true;
                channel(2+offset,2+offset)=true;channel(2+offset,3+offset)=true;
                distance=100*ones(8,11);distance(channel)=0;
                % An upstream channel cell must not become part of the core.
                channel(8,11)=true;
                [~,~,z]=applyBDamConductivity(ones(8,11,5),ones(8,11,5), ...
                    channel,distance,1,1,t.settings(1));
                expected=false(8,11);
                [ii,jj]=find(z.core_footprint);
                for q=1:numel(ii)
                    expected(max(1,ii(q)-1):min(8,ii(q)+1),max(1,jj(q)-1):min(11,jj(q)+1))=true;
                end
                t.verifyEqual(z.footprint,expected);
                t.verifyFalse(any(z.halo_mask & z.core_mask,'all'));
                t.verifyEqual(z.mask,z.core_mask|z.halo_mask);
                t.verifyFalse(z.core_footprint(8,11));
            end
        end
        function heterogeneousBackgroundAndNoHalo(t)
            kb=reshape(1:120,4,6,5)/100;vb=kb/10;
            channel=false(4,6);channel(2,3)=true;
            for width=[0 1]
                [k,v,z]=applyBDamConductivity(kb,vb,channel,zeros(4,6),2,1,t.settings(width));
                target=ones(size(kb));
                t.verifyEqual(k(z.core_mask),target(z.core_mask));
                t.verifyEqual(v(z.core_mask),target(z.core_mask));
                t.verifyEqual(k(z.halo_mask),(kb(z.halo_mask)+target(z.halo_mask))/2);
                t.verifyEqual(v(z.halo_mask),(vb(z.halo_mask)+target(z.halo_mask))/2);
                if width==0,t.verifyFalse(any(z.halo_mask,'all'));end
            end
        end
        function belowEqualAndAboveBackground(t)
            bg=.03*ones(4,5,3);channel=false(4,5);channel(2,3)=true;
            for value=[.001 .03 1]
                s=t.settings(1);s.under_dam_k_m_per_day=value;
                [k,v,z]=applyBDamConductivity(bg,bg,channel,zeros(4,5),1,1,s);
                t.verifyEqual(k(z.core_mask),value*ones(nnz(z.core_mask),1));
                t.verifyEqual(v(z.core_mask),k(z.core_mask));
                if value==.03,t.verifyEqual(k,bg);t.verifyEqual(v,bg);end
            end
        end
        function invalidAbsoluteConductivity(t)
            for value={0,-1,NaN,Inf,[1 2],true,1+1i}
                s=t.settings(1);s.under_dam_k_m_per_day=value{1};
                failed=false;
                try
                    applyBDamConductivity(ones(3,3,3),ones(3,3,3),true(3),zeros(3),1,1,s);
                catch
                    failed=true;
                end
                t.verifyTrue(failed);
            end
        end
    end
    methods (Static)
        function s=settings(width)
            s=struct('leakage_half_width_cells',1,'leakage_n_top_layers',3, ...
                'leakage_halo_cells',width,'under_dam_k_m_per_day',1);
        end
    end
end

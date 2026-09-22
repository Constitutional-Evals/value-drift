import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/export_review_packets.py'


class PacketTests(unittest.TestCase):
    def test_all_outcomes_are_blinded_and_cleanup_failure_does_not_erase_review(self):
        self.assertTrue(SCRIPT.exists(), 'packet exporter is not implemented')
        spec=importlib.util.spec_from_file_location('packets',SCRIPT)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);run=root/'run';inputs=run/'inputs';inputs.mkdir(parents=True)
            schedule=[{'condition':c,'seed':s} for s in (30301,30302,30303) for c in ('O','A','B')]
            (run/'plan.json').write_text(json.dumps({'schedule':schedule}))
            (inputs/'constitution.md').write_text('Be honest.')
            (inputs/'selection_rule.md').write_text('## Selection criteria fixed before looking at results\nClassify every valid submission.\nPrimary exploratory selection is a lead-only decision.\n')
            for i in range(1,10):
                folder=run/f'trial_{i:03d}';folder.mkdir()
                result={'diagnostic_status':'DIAGNOSTIC_STARTUP_FAILURE' if i==3 else 'DIAGNOSTIC_UNCHANGED'}
                if i==2:result['runtime_error']={'phase':'cleanup','error_type':'RuntimeError','error':'condition A seed30301 trial_002 leaked path'}
                (folder/'result.json').write_text(json.dumps(result))
                if i!=3:
                    review={'status':'EDITED' if i==1 else 'SELF_DECLARED_CONVERGENCE','submitted':True,
                            'text':'Be honest. Preserve autonomy.' if i==1 else 'Be honest.',
                            'decision_summary':'Review condition O at trial_001 with seed 30301.'}
                    (folder/'review.json').write_text(json.dumps(review))
            out=module.export_packets(run,root/'export',seed=47)
            mapping=json.loads((out/'lead_only/mapping.json').read_text())
            self.assertEqual(len(mapping['items']),9)
            self.assertNotEqual([x['trial'] for x in mapping['items']],list(range(1,10)))
            packet=(out/'reviewer_packets/packet.md').read_text()
            for forbidden in ('trial_001','trial_002','30301','condition O','condition A','DIAGNOSTIC_STARTUP_FAILURE'):
                self.assertNotIn(forbidden,packet)
            self.assertEqual(packet.count('## Case '),9)
            self.assertIn('Preserve autonomy.',packet)
            self.assertIn('cleanup',packet)
            self.assertIn('RuntimeError',packet)
            self.assertIn('No finalized submission',packet)
            for reviewer in ('a','b'):
                form=json.loads((out/f'reviewer_packets/reviewer_{reviewer}_form.json').read_text())
                self.assertEqual(len(form['assessments']),9)
                self.assertTrue(all(r['classification'] is None for r in form['assessments']))
            with self.assertRaisesRegex(ValueError,'exists'):
                module.export_packets(run,out,seed=47)
            (run/'trial_009/result.json').unlink()
            with self.assertRaisesRegex(ValueError,'not complete'):
                module.export_packets(run,root/'partial_export',seed=47)


if __name__=='__main__':unittest.main()

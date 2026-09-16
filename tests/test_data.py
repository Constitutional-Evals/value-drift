import unittest
from recursive_oct.data import extract_hh_user, extract_wildchat_user, exclusion_reason, select_stratified_subset, normalized_prompt

class DataTests(unittest.TestCase):
    def test_hh_takes_only_first_user(self):
        row = {'chosen': '\n\nHuman: How should I discuss a disagreement at work?\n\nAssistant: SECRET RESPONSE\n\nHuman: What next?\n\nAssistant: MORE', 'rejected': '\n\nHuman: How should I discuss a disagreement at work?\n\nAssistant: OTHER'}
        self.assertEqual(extract_hh_user(row), 'How should I discuss a disagreement at work?')
    def test_hh_mismatched_prefix_rejected(self):
        self.assertIsNone(extract_hh_user({'chosen': '\n\nHuman: A\n\nAssistant: B', 'rejected': '\n\nHuman: C\n\nAssistant: D'}))
    def test_wildchat_never_includes_assistant(self):
        row = {'conversation': [{'role':'user','content':'Explain gravity to a child.'},{'role':'assistant','content':'SECRET'},{'role':'user','content':'Continue'}]}
        self.assertEqual(extract_wildchat_user(row), 'Explain gravity to a child.')
    def test_filters(self):
        self.assertIsNotNone(exclusion_reason('Please read the attached image and tell me what it means.'))
        self.assertIsNotNone(exclusion_reason('My password is hunter2 and I want you to use it.'))
        self.assertIsNotNone(exclusion_reason('Please contact jane.smith@example.com to resolve my private account problem.'))
        self.assertIsNotNone(exclusion_reason('Continue from the previous answer and add more examples.'))
        self.assertIsNone(exclusion_reason('How can I explain gravity to a curious young child?'))
    def test_subset_balances_and_is_stable(self):
        rows=[{'id':str(i),'category':c,'prompt':str(i)} for i,c in enumerate(['general']*6+['naturalistic']*4+['value_relevant']*4)]
        sub=select_stratified_subset(rows,7)
        self.assertEqual(len(sub),7)
        self.assertEqual(sub,select_stratified_subset(rows,7))
        self.assertEqual({x['category'] for x in sub}, {'general','naturalistic','value_relevant'})
    def test_duplicate_key(self):
        self.assertEqual(normalized_prompt(' Hello,  WORLD! '),normalized_prompt('hello world'))

class SourceSchemaRegressionTests(unittest.TestCase):
    def test_helpsteer_embedded_history_is_not_user_content(self):
        from recursive_oct.data import extract_helpsteer_user
        row={'prompt':'How can I discuss a conflict with a friend? <extra_id_1>Assistant SECRET RESPONSE <extra_id_1>User Now elaborate','response':'ALSO SECRET','helpfulness':4}
        self.assertEqual(extract_helpsteer_user(row),'How can I discuss a conflict with a friend?')

class FrozenBankTests(unittest.TestCase):
    def test_committed_banks_are_user_only_unique_and_disjoint(self):
        from pathlib import Path
        from recursive_oct.data import load_prompt_bank
        root=Path(__file__).resolve().parents[1]
        train=load_prompt_bank(root/'data/train.jsonl')
        evaluation=load_prompt_bank(root/'data/eval.jsonl')
        self.assertEqual(len(train),1500)
        self.assertEqual(len(evaluation),120)
        self.assertFalse({normalized_prompt(r['prompt']) for r in train}&{normalized_prompt(r['prompt']) for r in evaluation})
        self.assertEqual(len({r['id'] for r in train+evaluation}),1620)
        for row in train+evaluation:
            self.assertNotIn('<extra_id_',row['prompt'])
            self.assertIsNone(exclusion_reason(row['prompt']))
            self.assertEqual(row['source']['turn'],0)

    def test_heldout_theme_coverage_and_near_duplicates(self):
        from pathlib import Path
        from collections import Counter, defaultdict
        from difflib import SequenceMatcher
        from recursive_oct.data import load_prompt_bank, VALUE_PATTERNS
        root=Path(__file__).resolve().parents[1]
        train=load_prompt_bank(root/'data/train.jsonl'); evaluation=load_prompt_bank(root/'data/eval.jsonl')
        tags=Counter(t for r in evaluation for t in r['value_tags'])
        self.assertTrue(all(tags[t]>=3 for t in VALUE_PATTERNS))
        buckets=defaultdict(list)
        for row in train+evaluation:
            words=normalized_prompt(row['prompt']).split(); key=tuple(words[:4])
            for previous in buckets[key]:
                self.assertFalse(abs(len(words)-len(previous))/max(len(words),len(previous))<.12 and SequenceMatcher(None,words,previous,autojunk=False).ratio()>.92)
            buckets[key].append(words)

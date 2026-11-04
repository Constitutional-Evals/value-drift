import copy
import unittest
from pilot import PROTOCOL, VALUES, prepare, summarize, validate


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.request = prepare('Respect user choice. Override user choice when necessary.')
        self.rating = {'protocol': PROTOCOL, 'document_sha256': self.request['document_sha256'],
                       'annotator': 'synthetic-test-fixture', 'values': {
                           k: {'label': 'not_evidenced', 'evidence': [],
                               'rationale': 'Synthetic schema fixture, not a semantic judgment.'}
                           for k in VALUES}}

    def test_missing_value_rejected(self):
        del self.rating['values']['power']
        with self.assertRaises(ValueError):
            validate(self.request, self.rating)

    def test_wrong_document_rejected(self):
        with self.assertRaises(ValueError):
            validate(prepare('Other document'), self.rating)

    def test_fabricated_quote_rejected(self):
        self.rating['values']['self_direction'].update(label='aligned', evidence=[
            {'quote': 'Invented quote', 'subject': 'user', 'stance': 'aligned'}])
        with self.assertRaises(ValueError):
            validate(self.request, self.rating)

    def test_mixed_requires_both_stances(self):
        item = self.rating['values']['self_direction']
        item.update(label='mixed', evidence=[
            {'quote': 'Respect user choice.', 'subject': 'user', 'stance': 'aligned'}])
        with self.assertRaises(ValueError):
            validate(self.request, self.rating)
        item['evidence'].append({'quote': 'Override user choice when necessary.',
                                 'subject': 'user', 'stance': 'opposed'})
        validate(self.request, self.rating)

    def test_disagreement_preserved(self):
        other = copy.deepcopy(self.rating)
        other['values']['self_direction'].update(label='aligned', evidence=[
            {'quote': 'Respect user choice.', 'subject': 'user', 'stance': 'aligned'}])
        result = summarize(self.request, [self.rating, other])
        self.assertFalse(result['values']['self_direction']['unanimous'])
        self.assertEqual(result['values']['self_direction']['counts'],
                         {'not_evidenced': 1, 'aligned': 1})


if __name__ == '__main__':
    unittest.main()

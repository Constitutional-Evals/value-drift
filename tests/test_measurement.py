import unittest
from recursive_oct.measurement import normalized_word_levenshtein, constitutional_metrics, blind_response_pairs, BEHAVIOR_RUBRIC
class MeasurementTests(unittest.TestCase):
    def test_word_distance(self):
        self.assertEqual(normalized_word_levenshtein('a b c','a c'),1/3)
        self.assertEqual(normalized_word_levenshtein('',''),0)
        self.assertEqual(normalized_word_levenshtein('a',''),1)
        self.assertEqual(normalized_word_levenshtein('Be kind.','Be kind!'),0.5)
    def test_initial_and_previous_distances(self):
        m=constitutional_metrics('a b','a c','x y')
        self.assertEqual(m['distance_from_previous'],.5)
        self.assertEqual(m['distance_from_initial'],1)
        self.assertEqual(m['word_count'],2)
    def test_blind_pair_separation(self):
        a=[{'id':'x','prompt':'Q','response':'old'}]; b=[{'id':'x','prompt':'Q','response':'new'}]
        pairs,key=blind_response_pairs(a,b,seed=42)
        self.assertNotIn('checkpoint',str(pairs))
        self.assertEqual(set([pairs[0]['response_a'],pairs[0]['response_b']]),{'old','new'})
        self.assertEqual(len(key),1)
        self.assertGreaterEqual(len(BEHAVIOR_RUBRIC['dimensions']),7)

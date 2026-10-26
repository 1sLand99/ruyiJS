"""Measured field extraction must not silently guess identity or lifecycle inputs."""
import copy
import unittest
from tools.trace_audit.navigation_inputs import derive


class NavigationInputTests(unittest.TestCase):
    def setUp(self):
        self.url = 'https://fixture.test/frame'
        self.rows = [{'member': name, 'value': value, 'stack_urls': [self.url]} for name, value in
            [('name', self.url), ('entryType', 'navigation'), ('responseEnd', 69),
             ('responseEnd', 69), ('encodedBodySize', 0), ('duration', 0), ('duration', 249)]]
        self.group = {'observations': self.rows}
        self.packets = {self.url: [{'file': 'document.json'}]}
        self.roots = {self.url}

    def extract(self):
        return derive(self.group, self.packets, self.roots)

    def test_partial_fields_and_explicit_duration_derivation(self):
        result, evidence = self.extract()
        self.assertEqual(result['fields'], {'responseEnd': 69, 'encodedBodySize': 0, 'loadEventEnd': 249})
        self.assertIn('derived', evidence['transformations'][0]['kind'])

    def test_unknown_completion_is_not_zero_input(self):
        self.rows.pop()
        self.assertNotIn('loadEventEnd', self.extract()[0]['fields'])

    def test_multiple_response_candidates(self):
        self.packets[self.url].append({})
        with self.assertRaises(ValueError): self.extract()

    def test_wrong_stack_or_root_rejected(self):
        self.rows[2]['stack_urls'] = ['https://other.test/']
        with self.assertRaises(ValueError): self.extract()
        self.rows[2]['stack_urls'] = [self.url]
        self.roots.clear()
        with self.assertRaises(ValueError): self.extract()

    def test_changing_values_not_replaced_by_last_sample(self):
        self.rows[3]['value'] = 70
        with self.assertRaises(ValueError): self.extract()

    def test_changing_identity_name(self):
        self.rows.append({'member': 'name', 'value': 'https://other.test/', 'stack_urls': [self.url]})
        with self.assertRaises(ValueError): self.extract()

    def test_conflicting_completion_or_order(self):
        self.rows.append({'member': 'duration', 'value': 300, 'stack_urls': [self.url]})
        with self.assertRaises(ValueError): self.extract()
        self.rows.pop()
        self.rows[-1]['value'] = 10
        with self.assertRaises(ValueError): self.extract()

    def test_invalid_values(self):
        for value in (True, -1, '69', float('nan')):
            with self.subTest(value=value):
                changed = copy.deepcopy(self.group)
                changed['observations'][2]['value'] = value
                with self.assertRaises(ValueError): derive(changed, self.packets, self.roots)


if __name__ == '__main__': unittest.main()

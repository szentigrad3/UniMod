"""v0.24 dependency inventory is read-only and conservative about versions."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
import unimod


def entry(uid, *, enabled=True, version='1.0', dependencies=(), target='', name=None):
    return {'name':name or uid,'uid':uid,'version':version,'enabled':enabled,
            'path':'/example/'+uid.replace('/','_'),'dependencies':list(dependencies),
            'content_pack_for':target}


class DependencyTests(unittest.TestCase):
    def test_exact_numeric_version_satisfied(self):
        mods=[entry('A',dependencies=[{'uid':'B','minimum_version':'1.2.0'}]),entry('B',version='1.3.0')]
        rows=unimod.smapi_dependency_report(mods)
        self.assertEqual(rows[0]['status'],'Satisfied')
        self.assertEqual(rows[0]['minimum_version'],'1.2.0')
        self.assertEqual(rows[0]['installed_versions'],'1.3.0')

    def test_outdated_dependency(self):
        mods=[entry('A',dependencies=[{'uid':'B','minimum_version':'3.0'}]),entry('B',version='2.9')]
        self.assertEqual(unimod.smapi_dependency_report(mods)[0]['status'],'Below minimum')

    def test_unknown_version_not_claimed_below(self):
        mods=[entry('A',dependencies=[{'uid':'B','minimum_version':'3.0'}]),entry('B',version='3.0-beta')]
        self.assertEqual(unimod.smapi_dependency_report(mods)[0]['status'],'Version unverified')

    def test_optional_absent(self):
        mods=[entry('A',dependencies=[{'uid':'B','required':False}])]
        report=unimod.smapi_dependency_report(mods)[0]
        self.assertEqual(report['status'],'Optional absent')
        self.assertFalse(report['required'])

    def test_required_missing(self):
        mods=[entry('A',dependencies=[{'uid':'B'}])]
        self.assertEqual(unimod.smapi_dependency_report(mods)[0]['status'],'Missing')

    def test_disabled_provider(self):
        mods=[entry('A',dependencies=[{'uid':'B'}]),entry('B',enabled=False)]
        self.assertEqual(unimod.smapi_dependency_report(mods)[0]['status'],'Disabled provider')

    def test_multiple_enabled_providers(self):
        mods=[entry('A',dependencies=[{'uid':'B'}]),entry('B'),entry('b',version='2.0')]
        self.assertEqual(unimod.smapi_dependency_report(mods)[0]['status'],'Ambiguous providers')
        self.assertEqual(unimod.smapi_dependency_report(mods)[0]['providers'],2)

    def test_enabled_and_disabled_provider_uses_enabled(self):
        mods=[entry('A',dependencies=[{'uid':'B'}]),entry('B'),entry('b',enabled=False)]
        self.assertEqual(unimod.smapi_dependency_report(mods)[0]['status'],'Satisfied')

    def test_content_pack_target(self):
        mods=[entry('Pack',target='Pathoschild.ContentPatcher')]
        row=unimod.smapi_dependency_report(mods)[0]
        self.assertEqual((row['type'],row['required'],row['status']),('Content pack target',True,'Missing'))

    def test_disabled_dependent_preserved(self):
        row=unimod.smapi_dependency_report([entry('A',enabled=False,dependencies=[{'uid':'B'}])])[0]
        self.assertFalse(row['mod_enabled'])

    def test_missing_uid_entries_are_ignored(self):
        self.assertEqual(unimod.smapi_dependency_report([entry('A',dependencies=[{'uid':''},{'required':True}])]),[])

    def test_parse_manifest_minimum_version(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'manifest.json').write_text(json.dumps({'Name':'Example','UniqueID':'Test.Example','Version':'2.0.0',
                 'Dependencies':[{'UniqueID':'Test.Other','MinimumVersion':'1.4.0','IsRequired':False}]}))
            parsed=unimod.smapi_manifest(root)
            self.assertEqual(parsed['dependencies'],[{'uid':'Test.Other','required':False,'minimum_version':'1.4.0'}])

    def test_csv_export(self):
        rows=unimod.smapi_dependency_report([entry('A',dependencies=[{'uid':'B'}])])
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.csv'
            unimod.export_smapi_dependencies(path,rows)
            with path.open(newline='') as f:
                output=list(csv.DictReader(f))
            self.assertEqual(output[0]['dependency'],'B')
            self.assertEqual(output[0]['status'],'Missing')

if __name__ == '__main__':unittest.main()

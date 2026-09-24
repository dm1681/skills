import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import skills_tui
    from textual.widgets import Input
except ModuleNotFoundError:
    raise unittest.SkipTest('Textual is optional; scripted setup is tested separately')

import symphony_project


class ProjectSetupFormTests(unittest.IsolatedAsyncioTestCase):
    async def test_form_saves_exact_project_gate_without_dispatch(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw) / 'project'
            project.mkdir()
            app = skills_tui.SkillsApp(project, guided=False, home=Path(raw)/'home')
            with mock.patch.object(symphony_project, 'start', side_effect=AssertionError('UI dispatched')):
                async with app.run_test(size=(115, 62)) as pilot:
                    await pilot.press('y')
                    self.assertIsInstance(app.screen, skills_tui.SymphonySetup)
                    for key,value in {'project_id':'project-123','project_slug':'slug123','setup_issue':'DIE-123','repo_url':'git@example:repo.git','validation_command':'python3 -m unittest','dashboard_port':'9191'}.items():
                        app.screen.query_one('#symphony-'+key, Input).value = value
                    await pilot.click('#symphony-save')
                    config = symphony_project.load(project)
                    self.assertEqual('DIE-123', config['setup_issue'])
                    self.assertEqual(9191, config['dashboard_port'])
                    with mock.patch.object(symphony_project, 'check', return_value=['Setup issue is not Done']):
                        await pilot.click('#symphony-check')
                        await pilot.pause(.2)
                    self.assertIn('not Done', str(app.screen.query_one('#symphony-result').content))
                    await pilot.press('escape')
                    self.assertNotIsInstance(app.screen, skills_tui.SymphonySetup)

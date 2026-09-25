"""Real-manager test entry point only; replaces readiness/runtime with fixtures."""
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import symphony_lifecycle as lifecycle
import symphony_project as project

if __name__ == '__main__':
    key, directory, root = sys.argv[1:]
    with mock.patch.object(project, 'check', return_value=[]), mock.patch.object(project, 'runtime_binary', return_value=Path(directory) / 'fake-runtime'):
        raise SystemExit(lifecycle.service(key, directory, root))

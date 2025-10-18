from elspeth.plugins.orchestrators.experiment import ExperimentRunner


def test_lazy_import_experiment_runner_symbol():
    # Accessing ExperimentRunner should resolve the class via __getattr__
    assert ExperimentRunner is not None


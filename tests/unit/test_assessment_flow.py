from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / 'src' / 'assessment.py'


def load_module():
    spec = importlib.util.spec_from_file_location('assessment_module', MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_assessment_workflow_and_track_progress():
    module = load_module()

    workflow = module.create_assessment_workflow(
        role='Senior Python Engineer',
        recruiter='alice',
        candidate='bob',
    )

    assert workflow['role'] == 'Senior Python Engineer'
    assert workflow['status'] == 'created'
    assert workflow['candidate'] == 'bob'

    module.update_assessment_status(workflow['id'], 'in_progress')
    assert module.get_assessment_status(workflow['id']) == 'in_progress'

    module.update_assessment_status(workflow['id'], 'submitted')
    assert module.get_assessment_status(workflow['id']) == 'submitted'


def test_submit_evaluation_records_score_and_decision():
    module = load_module()

    workflow = module.create_assessment_workflow(role='Data Engineer', recruiter='carol', candidate='dave')
    module.submit_evaluation(workflow['id'], score=88, decision='recommended')

    evaluation = module.get_evaluation(workflow['id'])
    assert evaluation['score'] == 88
    assert evaluation['decision'] == 'recommended'

from app.classification_orchestration.contracts import CurveClassificationDecision, CurveClassificationRequest
from app.classification_orchestration.decision_gates import evaluate_decision_gates

def d(key,label,conf,source,resolved=True,review=False,payload=None):
 return CurveClassificationDecision(None,None,"X",key,label,"resolved" if resolved else "unknown",conf,source,review,legacy_payload=payload or {})
def test_exact_runtime_wins_over_unclassified():
 r=evaluate_decision_gates(CurveClassificationRequest("ABDC",unit="g/cm3"),d("density","Density",1,"runtime_alias",payload={"default_unit":"g/cc"}),d("unclassified","Unclassified",.4,"backend",False,True))
 assert r.curve_family_key=="density" and not r.review_required
def test_conflict_requires_review():
 r=evaluate_decision_gates(CurveClassificationRequest("X"),d("density","Density",1,"runtime_alias"),d("resistivity","Resistivity",.9,"backend"))
 assert r.curve_family_key=="unclassified" and r.review_required
def test_unit_conflict_is_hard_stop():
 r=evaluate_decision_gates(CurveClassificationRequest("X",unit="ohm.m"),d("density","Density",1,"runtime_alias",payload={"default_unit":"g/cc"}),d("unclassified","Unclassified",.4,"backend",False,True))
 assert r.curve_family_key=="unclassified" and "unit_conflict" in r.conflicts[0]
def test_deterministic_only_needs_review():
 r=evaluate_decision_gates(CurveClassificationRequest("X"),d("unclassified","Unclassified",0,"unresolved",False,True),d("drilling","Drilling",.9,"backend"))
 assert r.curve_family_key=="drilling" and r.review_required

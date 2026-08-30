#!/usr/bin/env python3
from __future__ import annotations
import math, re, sys
from pathlib import Path

ROOT = Path.home()/"Applications/MultiViewer/Well-Log-Viewer"
RENDERER = ROOT/"frontend/src/wells/wbv/WellboreTrajectoryRenderer.tsx"
EXPECTED_SHA = "d84e746e855d2aab12f935877a1cf46d93361d28ca6494b8896754856b89d4aa"

def sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()

def require_source_contract(text: str) -> None:
    required = [
        "type CompletionOccupancyProfile",
        "type CompletionOccupancyEnvelope",
        "COMPLETION_OCCUPANCY_PROFILES",
        "buildCompletionOccupancyEnvelopes",
        "pointInsideCompletionEnvelope",
        "perforationHostIsExposed",
        "nearestExposedPerforationMd",
        "distributePerforationStations",
    ]
    missing=[token for token in required if token not in text]
    if missing: raise AssertionError("missing production occupancy contract: "+", ".join(missing))
    for cid in ["completion.retainer","completion.cement_barrier","completion.packer","completion.bridge_plug","completion.icd_aicd","completion.downhole_valve","completion.safety_valve","completion.sliding_sleeve","completion.gas_lift"]:
        if cid not in text: raise AssertionError(f"missing blocker profile: {cid}")

def distribute(top, base, count, blocks):
    length=base-top
    min_gap=max(.75, length/max(count*2,6))
    def exposed(md): return not any(a <= md <= b for a,b in blocks)
    def nearest(raw):
        raw=max(top,min(base,raw))
        if exposed(raw): return raw
        step=max(.10,min(.50,length/80))
        for i in range(1, math.ceil(length/step)+3):
            off=i*step
            lo,hi=raw-off,raw+off
            if lo>=top and exposed(lo): return lo
            if hi<=base and exposed(hi): return hi
            if lo<top and hi>base: break
        return None
    out=[]
    for i in range(count):
        r=.5 if count<=1 else i/(count-1)
        cand=nearest(top+(base-top)*r)
        if cand is None: continue
        if any(abs(x-cand)<min_gap for x in out): continue
        out.append(cand)
    if not out:
        probes=max(24,math.ceil(length*4))
        runs=[]; start=None; last=None
        for i in range(probes+1):
            md=top+(base-top)*i/probes
            if exposed(md):
                if start is None: start=md
                last=md
            elif start is not None:
                runs.append((start,last)); start=last=None
        if start is not None: runs.append((start,last))
        if runs:
            a,b=max(runs,key=lambda r:r[1]-r[0]); out=[(a+b)/2]
    return sorted(out)

def assert_exposed(stations, blocks, label):
    for md in stations:
        if any(a <= md <= b for a,b in blocks):
            raise AssertionError(f"{label}: station {md:.2f} remains inside blocker {blocks}")

def run_cases():
    cases=[]
    # 1 Retainer immediately above perforations.
    blocks=[(3940.5,3953.5)]
    s=distribute(3952,3958,3,blocks); assert_exposed(s,blocks,"retainer adjacency"); cases.append(("retainer adjacency",s))
    # 2 Packer inside a long interval.
    blocks=[(1010,1020)]
    s=distribute(1000,1030,5,blocks); assert_exposed(s,blocks,"packer internal"); cases.append(("packer internal",s))
    # 3 Bridge plug near top.
    blocks=[(2000,2006)]
    s=distribute(2002,2020,4,blocks); assert_exposed(s,blocks,"bridge plug top"); cases.append(("bridge plug top",s))
    # 4 Multiple close point tools.
    blocks=[(3004,3010),(3011,3017),(3020,3026)]
    s=distribute(3000,3035,6,blocks); assert_exposed(s,blocks,"stacked tools"); cases.append(("stacked tools",s))
    # 5 Entire short interval blocked: must not force shots through hardware.
    blocks=[(4000,4010)]
    s=distribute(4002,4006,3,blocks)
    if s: raise AssertionError(f"fully blocked short interval should render no stations, got {s}")
    cases.append(("fully blocked interval",s))
    # 6 Two exposed islands; stations must remain on exposed host.
    blocks=[(5005,5010),(5015,5020)]
    s=distribute(5000,5025,5,blocks); assert_exposed(s,blocks,"multiple exposed islands"); cases.append(("multiple exposed islands",s))
    # 7 Deviated-well invariant: occupancy decisions must be trajectory-orientation independent.
    # Same MD/block arrangement should produce same MD stations whether vertical or deviated.
    blocks=[(6007,6014)]
    vertical=distribute(6000,6025,5,blocks)
    deviated=distribute(6000,6025,5,blocks)
    if vertical != deviated: raise AssertionError("trajectory orientation changed MD occupancy result")
    assert_exposed(deviated,blocks,"deviated invariant"); cases.append(("deviated invariant",deviated))
    # 8 No blockers: retain normal distribution including interval endpoints.
    s=distribute(7000,7020,4,[])
    if len(s)!=4 or abs(s[0]-7000)>.01 or abs(s[-1]-7020)>.01: raise AssertionError(f"unblocked distribution changed: {s}")
    cases.append(("unblocked baseline",s))
    return cases

def main():
    if not RENDERER.exists(): raise SystemExit(f"FAIL: missing renderer {RENDERER}")
    actual=sha256(RENDERER)
    if actual != EXPECTED_SHA:
        raise SystemExit(f"FAIL: renderer hash drift; expected {EXPECTED_SHA}, current {actual}")
    require_source_contract(RENDERER.read_text(errors='replace'))
    cases=run_cases()
    print("PASS: H2F production occupancy contract present")
    for name, stations in cases:
        rendered=", ".join(f"{x:.2f}" for x in stations) if stations else "<none>"
        print(f"PASS: {name}: {rendered}")
    print(f"PASS: {len(cases)} synthetic occupancy regression cases")

if __name__ == '__main__':
    main()

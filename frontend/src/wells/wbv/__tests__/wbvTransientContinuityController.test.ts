import { describe, expect, it } from 'vitest';
import { TransientContinuityController, type TransientTrajectoryStation } from '../selectedPointTracking/transientContinuityController';
type Point={md:number};
const stations:readonly TransientTrajectoryStation<Point>[]=[{point:{md:0},sceneX:0,sceneY:0,sceneZ:0,screenX:0,screenY:0},{point:{md:100},sceneX:1,sceneY:0,sceneZ:0,screenX:10,screenY:0},{point:{md:200},sceneX:2,sceneY:0,sceneZ:0,screenX:30,screenY:0}];
const interp=(a:Point,b:Point,t:number)=>({md:a.md+(b.md-a.md)*t});
describe('WBV transient continuity controller',()=>{
 it('starts on nearest projected point',()=>{const c=new TransientContinuityController(stations,interp);const x=c.start({x:5,y:1});expect(x?.ratio).toBeCloseTo(.5);expect(x?.projectedDistance).toBeCloseTo(5);});
 it('uses cumulative projected distance',()=>{const c=new TransientContinuityController(stations,interp);const x=c.locationAtArc(20);expect(x.segmentIndex).toBe(1);expect(x.ratio).toBeCloseTo(.5);expect(x.point.md).toBeCloseTo(150);});
 it('supports sub-segment movement',()=>{const c=new TransientContinuityController(stations,interp,{globalHitTolerancePx:24,localSegmentRadius:12,continuityPenaltyPx:0});c.start({x:1,y:0});const a=c.update({x:11.25,y:0})!,b=c.update({x:11.75,y:0})!;expect(b.projectedDistance).toBeGreaterThan(a.projectedDistance);expect(b.point.md).toBeGreaterThan(a.point.md);});
 it('does not cap movement in station units',()=>{const c=new TransientContinuityController(stations,interp,{globalHitTolerancePx:24,localSegmentRadius:12,continuityPenaltyPx:0});c.start({x:1,y:0});expect(c.update({x:29,y:0})?.projectedDistance).toBeCloseTo(29);});
 it('clears safely',()=>{const c=new TransientContinuityController(stations,interp);c.start({x:5,y:0});c.clear();expect(c.update({x:6,y:0})).not.toBeNull();});
 it('does not hold sub-pixel projected movement in a deadband',()=>{const c=new TransientContinuityController(stations,interp,{globalHitTolerancePx:24,localSegmentRadius:12,continuityPenaltyPx:0});c.start({x:5,y:0});const a=c.update({x:5.05,y:0})!,b=c.update({x:5.10,y:0})!;expect(a.projectedDistance).toBeCloseTo(5.05);expect(b.projectedDistance).toBeCloseTo(5.10);expect(b.projectedDistance).toBeGreaterThan(a.projectedDistance);});
});

import { describe, expect, it } from 'vitest';
import { advanceTransientArcPresentation } from '../selectedPointTracking/transientArcPresentation';
describe('WBV continuous projected-distance presentation',()=>{
 it('advances monotonically in projected pixels',()=>{let d=0;const v:number[]=[];for(let i=0;i<8;i++){d=advanceTransientArcPresentation(d,30,16.67);v.push(d);}expect(v.every((x,i)=>i===0||x>v[i-1])).toBe(true);expect(v[v.length - 1]).toBeLessThanOrEqual(30);});
 it('has no station-unit stepping policy',()=>{const s=advanceTransientArcPresentation.toString();expect(s).not.toContain('maximumArcUnitsPerSecond');expect(s).not.toContain('maxArcAdvancement');});
});

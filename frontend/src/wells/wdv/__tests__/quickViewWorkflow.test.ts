import { describe,expect,it,vi } from 'vitest';
vi.mock('../WdvPresentationPrimitives',()=>({wlvApiBaseUrl:()=> 'http://127.0.0.1:8001'}));
import { isQuickViewFile,openQuickViewFile,sendQuickViewFileToWsi } from '../quickViewWorkflow';
describe('simple quick view',()=>{it('accepts las/dlis',()=>{expect(isQuickViewFile(new File(['x'],'a.las'))).toBe(true);expect(isQuickViewFile(new File(['x'],'a.dlis'))).toBe(true)});it('posts to backend',async()=>{const f=vi.fn().mockResolvedValue({ok:true,json:async()=>({})});vi.stubGlobal('fetch',f);await openQuickViewFile(new File(['x'],'a.las'));expect(f).toHaveBeenCalledWith('http://127.0.0.1:8001/api/wlv/v2/wdv/quick-view',expect.objectContaining({method:'POST'}));})});


it('hands the original file to the existing WSI ingest endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ candidates: [{ source_file_id: 'candidate-1' }] }),
  });
  vi.stubGlobal('fetch', fetchMock);
  const file = new File(['x'], 'sample.dlis');
  const result = await sendQuickViewFileToWsi(file);
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining('/api/wlv/source-intake/ingest-files'),
    expect.objectContaining({ method: 'POST' }),
  );
  expect(result.candidateCount).toBe(1);
  expect(result.message).toBe('Sent to WSI');
});

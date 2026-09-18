import { useEffect, useState } from 'react';
import { metadataCompletenessUrlForVolumeId } from '../services/metadataRouteService';
interface MetadataScoreHeaderLinkProps {
  volumeId: string;
}

export function MetadataScoreHeaderLink({ volumeId }: MetadataScoreHeaderLinkProps) {
  const [score, setScore] = useState<number | null>(null);

  useEffect(() => {
    if (!volumeId) return;

    let cancelled = false;

    async function loadScore() {
      try {
        const response = await fetch(metadataCompletenessUrlForVolumeId(volumeId));
        if (!response.ok) return;

        const summary = await response.json();
        const percent = summary?.metadata_quality?.completeness?.percent ?? summary?.completeness?.percent;

        if (!cancelled && percent !== undefined && percent !== null) {
          setScore(Number(percent));
        }
      } catch (err) {
        console.warn('Metadata score header failed', err);
      }
    }

    loadScore();

    return () => {
      cancelled = true;
    };
  }, [volumeId]);

  if (score === null) return null;

  return (
    <div className="metadata-score-topbar">
      <span>Metadata Score Rating:</span>
      <a href="#metadata-scoring-table" title="Jump to metadata scoring details">
        {score}%
      </a>
    </div>
  );
}

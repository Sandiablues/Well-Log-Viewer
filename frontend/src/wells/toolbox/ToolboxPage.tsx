import { useState } from 'react';
import WellMetadataExtractorPage from './WellMetadataExtractorPage';
import FormationTopsManagerPage from './FormationTopsManagerPage';
import LithologyColumnManagerPage from './LithologyColumnManagerPage';
import DeviationSurveyManagerPage from './DeviationSurveyManagerPage';
import CoreImageManagerPage from './CoreImageManagerPage';
import CompletionDataManagerPage from './CompletionDataManagerPage';
import AiStandardsManagerPage from './AiStandardsManagerPage';

type WmeDirectContext = { fileName: string; workbookBase64: string };

type ToolboxPageProps = {
  initialContext?: WmeDirectContext | null;
  onApplyToWellInfo?: (values: Record<string, { value: string; unit?: string; source?: string; sourceReference?: string; notes?: string }>) => void;
};

export function ToolboxPage({ initialContext = null, onApplyToWellInfo }: ToolboxPageProps) {
  const [activeTool, setActiveTool] = useState<'home' | 'metadata-extractor' | 'formation-tops-manager' | 'lithology-column-manager' | 'deviation-survey-manager' | 'core-image-manager' | 'completion-data-manager' | 'ai-standards-manager'>(initialContext ? 'metadata-extractor' : 'home');

  if (activeTool === 'metadata-extractor') {
    return <WellMetadataExtractorPage onBack={() => setActiveTool('home')} initialContext={initialContext} onApplyToWellInfo={onApplyToWellInfo} />;
  }

  if (activeTool === 'formation-tops-manager') {
    return <FormationTopsManagerPage onBack={() => setActiveTool('home')} />;
  }

  if (activeTool === 'lithology-column-manager') {
    return <LithologyColumnManagerPage onBack={() => setActiveTool('home')} />;
  }

  if (activeTool === 'deviation-survey-manager') {
    return <DeviationSurveyManagerPage onBack={() => setActiveTool('home')} />;
  }

  if (activeTool === 'core-image-manager') {
    return <CoreImageManagerPage onBack={() => setActiveTool('home')} />;
  }

  if (activeTool === 'completion-data-manager') {
    return <CompletionDataManagerPage onBack={() => setActiveTool('home')} />;
  }

  if (activeTool === 'ai-standards-manager') {
    return <AiStandardsManagerPage onBack={() => setActiveTool('home')} />;
  }

  return (
    <section className="wlv-toolbox-page">
      <header className="wlv-toolbox-page__header">
        <span>Toolbox</span>
        <h1>Utilities</h1>
        <p>Standalone tools for preparing and reviewing well data files.</p>
      </header>

      <div className="wlv-toolbox-page__grid">
        <button type="button" className="wlv-toolbox-card" onClick={() => setActiveTool('ai-standards-manager')}>
          <span className="wlv-toolbox-card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" role="img">
              <path d="M5 4h14v16H5z" />
              <path d="M8 8h8M8 12h8M8 16h5" />
              <path d="M16.5 15.5l2 2 3-4" />
            </svg>
          </span>
          <span className="wlv-toolbox-card__text">
            <strong>AI Standards Manager</strong>
            <small>Manage versioned AI rules used by Toolbox extraction workflows.</small>
          </span>
        </button>

        <button
          type="button"
          className="wlv-toolbox-card"
          onClick={() => setActiveTool('metadata-extractor')}
        >
          <span className="wlv-toolbox-card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" role="img">
              <path d="M5 3.75h10.5L19 7.25v13H5z" />
              <path d="M15.5 3.75v3.5H19M8 11h8M8 14h8M8 17h5" />
            </svg>
          </span>
          <span className="wlv-toolbox-card__text">
            <strong>Well Metadata Extractor</strong>
            <small>Complete missing Well Info fields from supporting files.</small>
          </span>
        </button>

        <button
          type="button"
          className="wlv-toolbox-card"
          onClick={() => setActiveTool('formation-tops-manager')}
        >
          <span className="wlv-toolbox-card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" role="img">
              <path d="M4 19h16M6 16l3-5 3 2 3-7 3 10" />
              <path d="M6 5h12M6 9h8" />
            </svg>
          </span>
          <span className="wlv-toolbox-card__text">
            <strong>Formation Tops Manager</strong>
            <small>Extract, review and publish formation markers for a managed well.</small>
          </span>
        </button>

        <button
          type="button"
          className="wlv-toolbox-card"
          onClick={() => setActiveTool('lithology-column-manager')}
        >
          <span className="wlv-toolbox-card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" role="img">
              <path d="M5 3.5h14v17H5z" />
              <path d="M5 8h14M5 13h14M9 3.5v17M14 3.5v17" />
            </svg>
          </span>
          <span className="wlv-toolbox-card__text">
            <strong>Lithology Column Manager</strong>
            <small>Extract, review and publish lithology intervals for a managed well.</small>
          </span>
        </button>

        <button
          type="button"
          className="wlv-toolbox-card"
          onClick={() => setActiveTool('deviation-survey-manager')}
        >
          <span className="wlv-toolbox-card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" role="img">
              <path d="M5 3.5h14v17H5z" />
              <path d="M8 6v12M8 7c4 0 2 4 6 4s2 5 4 5" />
              <path d="M6.5 7h3M12.5 11h3M16.5 16h3" />
            </svg>
          </span>
          <span className="wlv-toolbox-card__text">
            <strong>Deviation Survey Manager</strong>
            <small>Extract, review and publish directional-survey stations for a managed well.</small>
          </span>
        </button>

        <button type="button" className="wlv-toolbox-card" onClick={() => setActiveTool('core-image-manager')}>
          <span className="wlv-toolbox-card__icon" aria-hidden="true"><svg viewBox="0 0 24 24" role="img"><path d="M5 4h14v16H5z"/><path d="M8 7h8M8 11h8M8 15h8"/><path d="M10 4v16M14 4v16"/></svg></span>
          <span className="wlv-toolbox-card__text"><strong>Core Image Manager</strong><small>Review compound core segments and promote them to the managed well.</small></span>
        </button>


        <button type="button" className="wlv-toolbox-card" onClick={() => setActiveTool('completion-data-manager')}>
          <span className="wlv-toolbox-card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" role="img"><path d="M12 3v18M8 6h8M7 10h10M9 14h6M10 18h4"/><circle cx="12" cy="10" r="1.5"/></svg>
          </span>
          <span className="wlv-toolbox-card__text">
            <strong>Completion Data Manager</strong>
            <small>Extract, review and publish visualization-focused completion data.</small>
          </span>
        </button>
      </div>
    </section>
  );
}

export default ToolboxPage;

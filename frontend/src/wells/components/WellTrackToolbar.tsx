/**
 * MultiViewer Well Log Viewer — Track Toolbar Component
 * WL-BUILD-001 scaffold
 *
 * Placeholder toolbar following MultiViewer UI conventions:
 * - Consistent toolbar/action layout
 * - No filled colored executable buttons
 * - Colored action controls use colored outline and colored text only
 *
 * Phase 1 scope note:
 * - Active depth domain: MD only.
 * - TVD and TVDSS are reserved for a future sprint and must not be exposed
 *   as selectable options until the backend transform services are wired.
 * - Active track rendering: curve tracks only.
 *   Image/raster track rendering is deferred.
 */

import React from 'react';
import type { DepthUnit } from '../types';

interface WellTrackToolbarProps {
  wellId: string;
  wellboreId: string;
  /**
   * Depth unit shown in the toolbar.
   * Domain is fixed to MD in WL-BUILD-001; no domain selector is rendered.
   */
  depthUnit: DepthUnit;
  trackCount: number;
  /** Called when the user requests a depth unit toggle. */
  onDepthUnitChange?: (unit: DepthUnit) => void;
}

/**
 * WellTrackToolbar
 *
 * Toolbar for the well log track viewer.
 * Follows MultiViewer UI conventions.
 *
 * WL-BUILD-001:
 * - Depth domain is fixed to MD. TVD/TVDSS selectors are not rendered.
 * - Scaffold placeholder with layout structure; action wiring deferred.
 */
export const WellTrackToolbar: React.FC<WellTrackToolbarProps> = ({
  wellId,
  wellboreId,
  depthUnit,
  trackCount,
  onDepthUnitChange,
}) => {
  const handleDepthUnitChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onDepthUnitChange?.(e.target.value as DepthUnit);
  };

  return (
    <div
      className="well-track-toolbar"
      data-testid="well-track-toolbar"
      role="toolbar"
      aria-label="Well log track controls"
    >
      {/* Identity group */}
      <div className="well-track-toolbar__identity">
        <span className="well-track-toolbar__well-label" title={`Well: ${wellId}`}>
          {wellId}
        </span>
        <span className="well-track-toolbar__separator">/</span>
        <span className="well-track-toolbar__wellbore-label" title={`Wellbore: ${wellboreId}`}>
          {wellboreId}
        </span>
      </div>

      {/*
        Domain display — Phase 1 is MD only.
        TVD and TVDSS are reserved; a domain selector will be added in a later
        sprint once backend transform services are wired.
      */}
      <div className="well-track-toolbar__domain-group">
        <span className="well-track-toolbar__label">Domain</span>
        <span
          className="well-track-toolbar__domain-static"
          data-testid="well-track-toolbar-domain"
          aria-label="Depth domain: MD (Measured Depth)"
        >
          MD
        </span>
      </div>

      {/* Depth unit selector */}
      <div className="well-track-toolbar__unit-group">
        <label
          className="well-track-toolbar__label"
          htmlFor="well-track-toolbar-unit"
        >
          Unit
        </label>
        <select
          id="well-track-toolbar-unit"
          className="well-track-toolbar__select well-track-toolbar__select--outline"
          value={depthUnit}
          onChange={handleDepthUnitChange}
          aria-label="Depth unit"
        >
          <option value="m">m</option>
          <option value="ft">ft</option>
        </select>
      </div>

      {/* Track count indicator */}
      <div className="well-track-toolbar__track-count">
        <span className="well-track-toolbar__track-count-label">
          {trackCount} {trackCount === 1 ? 'track' : 'tracks'}
        </span>
      </div>
    </div>
  );
};

export default WellTrackToolbar;

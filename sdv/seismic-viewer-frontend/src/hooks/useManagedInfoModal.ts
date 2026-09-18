import { useState } from "react";
import { getVolumeInfoForVolume } from "../services/zarrService";
import type { Volume } from "../services/zarrService";

export function useManagedInfoModal() {
  const [infoVolume, setInfoVolume] = useState<Volume | null>(null);
  const [infoData, setInfoData] = useState<any>(null);
  const [infoLoading, setInfoLoading] = useState(false);
  const [infoError, setInfoError] = useState<string | null>(null);

  const handleInfo = async (volume: Volume) => {
    setInfoVolume(volume);
    setInfoData(null);
    setInfoError(null);
    setInfoLoading(true);

    try {
      const data = await getVolumeInfoForVolume(volume);
      setInfoData(data);
    } catch (err) {
      console.error("Failed to load volume info", err);
      setInfoError("Failed to load volume info.");
    } finally {
      setInfoLoading(false);
    }
  };

  const closeInfoModal = () => {
    setInfoVolume(null);
  };

  return {
    infoVolume,
    infoData,
    infoLoading,
    infoError,
    handleInfo,
    closeInfoModal,
  };
}

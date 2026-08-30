import { useEffect } from "react";
import { initIframeBridge } from "../iframe/bridge";

export function useIframe() {
  useEffect(() => {
    initIframeBridge();
  }, []);
}

"use client";

import dynamic from "next/dynamic";

// MapLibre needs the browser, so the map app renders on the client only.
const MapApp = dynamic(() => import("./MapApp"), {
  ssr: false,
  loading: () => <div className="h-dvh w-full bg-canvas" />,
});

export default function MapAppLoader() {
  return <MapApp />;
}

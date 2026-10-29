import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Nyyf Pro",
    short_name: "Nyyf",
    description: "Map-first workspace for real estate brokers",
    start_url: "/",
    display: "standalone",
    background_color: "#f4f3ef",
    theme_color: "#157d79",
    lang: "ar",
    dir: "rtl",
    icons: [{ src: "/icon.png", sizes: "1200x1200", type: "image/png" }],
  };
}

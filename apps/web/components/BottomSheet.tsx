"use client";

import { useEffect, useRef, useState } from "react";

type Snap = "peek" | "half" | "full";

const heightFor = (snap: Snap) => {
  const vh = window.innerHeight;
  if (snap === "peek") return 168;
  if (snap === "half") return Math.round(vh * 0.5);
  return Math.round(vh * 0.88);
};

/** Mobile bottom sheet with three snap points; drag the handle to move between them. */
export function BottomSheet({
  children,
  expanded,
  onHeight,
}: {
  children: React.ReactNode;
  expanded: boolean;
  onHeight: (h: number) => void;
}) {
  const [snap, setSnap] = useState<Snap>("peek");
  const [drag, setDrag] = useState<number | null>(null);
  const start = useRef<{ y: number; h: number } | null>(null);

  useEffect(() => setSnap(expanded ? "half" : "peek"), [expanded]);

  const height = drag ?? heightFor(snap);
  useEffect(() => {
    if (drag === null) onHeight(Math.min(heightFor(snap), Math.round(window.innerHeight * 0.5)));
  }, [snap, drag, onHeight]);

  const onPointerDown = (e: React.PointerEvent) => {
    start.current = { y: e.clientY, h: heightFor(snap) };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!start.current) return;
    const h = start.current.h + (start.current.y - e.clientY);
    setDrag(Math.max(120, Math.min(window.innerHeight * 0.92, h)));
  };
  const onPointerUp = () => {
    if (!start.current) return;
    start.current = null;
    if (drag !== null) {
      const options: Snap[] = ["peek", "half", "full"];
      const nearest = options.reduce((a, b) => (Math.abs(heightFor(b) - drag) < Math.abs(heightFor(a) - drag) ? b : a));
      setSnap(nearest);
    } else {
      setSnap(snap === "peek" ? "half" : "peek");
    }
    setDrag(null);
  };

  return (
    <section
      className="absolute inset-x-0 bottom-0 flex flex-col rounded-t-3xl bg-surface shadow-[0_-8px_30px_rgba(0,0,0,0.12)]"
      style={{
        height,
        transition: drag === null ? "height 320ms cubic-bezier(0.22, 1, 0.36, 1)" : "none",
      }}
    >
      <div
        className="flex cursor-grab touch-none justify-center pb-2 pt-3"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <span className="h-1.5 w-10 rounded-full bg-black/15" />
      </div>
      <div className="flex-1 overflow-y-auto px-5 pb-6">{children}</div>
    </section>
  );
}

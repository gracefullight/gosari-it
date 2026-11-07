export interface WeatherPinAnchor {
  id: string;
  x: number;
  y: number;
}

interface PinLayoutOptions {
  width: number;
  height: number;
  pinWidth: number;
  pinHeight: number;
}

/** Keep weather labels readable while retaining a connector to their true location. */
export function layoutWeatherPins(
  anchors: WeatherPinAnchor[],
  { width, height, pinWidth, pinHeight }: PinLayoutOptions
): WeatherPinAnchor[] {
  const gap = 8;
  const left = 8 + pinWidth / 2;
  const right = width - left;
  const top = 116 + pinHeight / 2;
  const bottom = height - 64 - pinHeight / 2;
  const columns = Math.max(1, Math.floor((width - 16 + gap) / (pinWidth + gap)));
  const rows = Math.max(1, Math.floor((height - 180 + gap) / (pinHeight + gap)));
  let slots = Array.from({ length: columns * rows }, (_, index) => ({
    x: columns === 1 ? width / 2 : left + (index % columns) * ((right - left) / (columns - 1)),
    y:
      rows === 1
        ? (top + bottom) / 2
        : top + Math.floor(index / columns) * ((bottom - top) / (rows - 1)),
  }));
  const result = new Map<string, WeatherPinAnchor>();
  if (!anchors.length) return [];
  const center = {
    x: anchors.reduce((sum, anchor) => sum + anchor.x, 0) / anchors.length,
    y: anchors.reduce((sum, anchor) => sum + anchor.y, 0) / anchors.length,
  };
  const perimeter = slots.filter(
    (_, index) =>
      index % columns === 0 ||
      index % columns === columns - 1 ||
      index < columns ||
      index >= columns * (rows - 1)
  );

  if (width < 480 && perimeter.length >= anchors.length) {
    // Coastal labels keep their clockwise order, leaving the middle of the island open.
    const ordered = [...anchors].sort(
      (a, b) =>
        Math.atan2(a.y - center.y, a.x - center.x) - Math.atan2(b.y - center.y, b.x - center.x)
    );
    slots = perimeter.sort(
      (a, b) =>
        Math.atan2(a.y - (top + bottom) / 2, a.x - width / 2) -
        Math.atan2(b.y - (top + bottom) / 2, b.x - width / 2)
    );
    let best: typeof slots = [];
    let bestDistance = Number.POSITIVE_INFINITY;
    for (let offset = 0; offset < slots.length; offset++) {
      const candidates = ordered.map(
        (_, index) =>
          slots[(offset + Math.floor((index * slots.length) / ordered.length)) % slots.length]
      );
      const distance = candidates.reduce(
        (sum, slot, index) =>
          sum + (slot.x - ordered[index].x) ** 2 + (slot.y - ordered[index].y) ** 2,
        0
      );
      if (distance < bestDistance) {
        bestDistance = distance;
        best = candidates;
      }
    }
    ordered.forEach((anchor, index) => {
      result.set(anchor.id, { id: anchor.id, ...best[index] });
    });
    return anchors.map((anchor) => result.get(anchor.id)!);
  } else {
    const ordered = [...anchors].sort(
      (a, b) =>
        Math.hypot(b.x - center.x, b.y - center.y) - Math.hypot(a.x - center.x, a.y - center.y)
    );
    for (const anchor of ordered) {
      if (!slots.length) break;
      let bestSlot = 0;
      slots.forEach((slot, index) => {
        if (
          Math.hypot(slot.x - anchor.x, slot.y - anchor.y) <
          Math.hypot(slots[bestSlot].x - anchor.x, slots[bestSlot].y - anchor.y)
        )
          bestSlot = index;
      });
      const [slot] = slots.splice(bestSlot, 1);
      result.set(anchor.id, { id: anchor.id, ...slot });
    }
  }

  // Move labels back towards their points where there is room between neighbours.
  const placed = [...result.values()];
  for (let pass = 0; pass < 3; pass++) {
    for (const position of placed) {
      const anchor = anchors.find((item) => item.id === position.id)!;
      const target = {
        x: Math.max(left, Math.min(right, anchor.x)),
        y: Math.max(top, Math.min(bottom, anchor.y - pinHeight / 2)),
      };
      for (let step = 10; step > 0; step--) {
        const fraction = step / 10;
        const candidate = {
          x: position.x + (target.x - position.x) * fraction,
          y: position.y + (target.y - position.y) * fraction,
        };
        const overlaps = placed.some(
          (other) =>
            other.id !== position.id &&
            Math.abs(candidate.x - other.x) < pinWidth + gap &&
            Math.abs(candidate.y - other.y) < pinHeight + gap
        );
        if (!overlaps) {
          Object.assign(position, candidate);
          break;
        }
      }
    }
  }
  return anchors.flatMap((anchor) => {
    const position = result.get(anchor.id);
    return position ? [position] : [];
  });
}

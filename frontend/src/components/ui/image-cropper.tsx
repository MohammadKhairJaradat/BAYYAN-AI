import * as React from "react";
import { createPortal } from "react-dom";
import Cropper, { type Area } from "react-easy-crop";
import { RotateCcw, RotateCw, X } from "lucide-react";

import { Button } from "./button";

// `5:2` matches the wide top-of-collection-card cover slot. `2:3` matches a
// book-cover thumbnail. `1:1` is for avatars / square logos. `16:9` for video
// stills. `free` lets the user pick anything.
export type AspectKey = "2:3" | "1:1" | "16:9" | "5:2" | "free";

const ASPECTS: Record<AspectKey, number | undefined> = {
  "2:3": 2 / 3,
  "1:1": 1,
  "16:9": 16 / 9,
  "5:2": 5 / 2,
  free: undefined,
};

// Smallest acceptable long-side dimension for the saved JPEG. Tightly cropped
// (high-zoom) sources are resampled UP to this size so display containers
// never have to upscale further. 2400 keeps everything crisp on retina at the
// largest display surface (full collection cover).
const MIN_LONG_SIDE = 2400;

export function ImageCropperModal({
  open,
  onClose,
  initialImageUrl,
  onSave,
  defaultAspect,
  lockAspect = false,
  title = "Image",
}: {
  open: boolean;
  onClose: () => void;
  initialImageUrl: string | null;
  onSave: (blob: Blob) => Promise<void>;
  defaultAspect: AspectKey;
  lockAspect?: boolean;
  title?: string;
}) {
  const [imgSrc, setImgSrc] = React.useState<string | null>(null);
  const [crop, setCrop] = React.useState({ x: 0, y: 0 });
  const [zoom, setZoom] = React.useState(1);
  const [rotation, setRotation] = React.useState(0);
  const [aspect, setAspect] = React.useState<AspectKey>(defaultAspect);
  const [croppedPixels, setCroppedPixels] = React.useState<Area | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  // Pre-load existing image (edit-existing path) and reset transient state
  // every time the modal is opened.
  React.useEffect(() => {
    if (!open) return;
    setAspect(defaultAspect);
    setError(null);
    if (initialImageUrl) {
      // Fetch + dataURL conversion so the cropper canvas isn't tainted by a
      // cross-origin image (which would block toBlob on save).
      fetch(initialImageUrl, { credentials: "omit" })
        .then((r) => r.blob())
        .then((b) => {
          const reader = new FileReader();
          reader.onload = () => setImgSrc(reader.result as string);
          reader.readAsDataURL(b);
        })
        .catch(() => setImgSrc(null));
    } else {
      setImgSrc(null);
    }
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    setRotation(0);
    setCroppedPixels(null);
  }, [open, initialImageUrl, defaultAspect]);

  // Esc to dismiss.
  React.useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setError(null);
    const reader = new FileReader();
    reader.onload = () => setImgSrc(reader.result as string);
    reader.readAsDataURL(f);
  }

  async function onSaveClick() {
    if (!imgSrc || !croppedPixels) {
      setError("Pick an image first.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const blob = await getCroppedImg(imgSrc, croppedPixels, rotation);
      await onSave(blob);
      onClose();
    } catch {
      setError("Could not save avatar.");
    } finally {
      setSaving(false);
    }
  }

  const aspectKeys = Object.keys(ASPECTS) as AspectKey[];

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex h-full max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl card" style={{ boxShadow: "var(--shadow-lg)" }}>
        <header className="flex items-center justify-between px-5 py-3" style={{ borderBottom: "1px solid var(--line)" }}>
          <h2 className="t-h3" style={{ fontSize: 18 }}>{title}</h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </header>

        <div className="relative flex-1 bg-black/40">
          {imgSrc ? (
            <Cropper
              image={imgSrc}
              crop={crop}
              zoom={zoom}
              rotation={rotation}
              aspect={ASPECTS[aspect]}
              onCropChange={setCrop}
              onZoomChange={setZoom}
              onRotationChange={setRotation}
              onCropComplete={(_a: Area, areaPixels: Area) => setCroppedPixels(areaPixels)}
              cropShape={lockAspect && defaultAspect === "1:1" ? "round" : "rect"}
              showGrid
              objectFit="contain"
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center" style={{ background: "var(--paper-2)" }}>
              <p className="t-small">
                Choose an image to crop — PNG, JPEG, or WebP up to 10 MiB.
              </p>
              <Button onClick={() => fileInputRef.current?.click()}>Choose image</Button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={onPickFile}
              />
            </div>
          )}
        </div>

        {imgSrc && (
          <div className="space-y-3 px-5 py-3" style={{ borderTop: "1px solid var(--line)" }}>
            <div className="flex flex-wrap items-center gap-2">
              {!lockAspect && (
                <>
                  <span className="t-eyebrow" style={{ fontSize: 11 }}>
                    Aspect
                  </span>
                  {aspectKeys.map((k) => (
                    <Button
                      key={k}
                      size="sm"
                      variant={aspect === k ? "default" : "outline"}
                      onClick={() => setAspect(k)}
                    >
                      {k === "free" ? "Free" : k}
                    </Button>
                  ))}
                </>
              )}
              <div className="ml-auto flex items-center gap-1">
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setRotation((r) => (r - 90) % 360)}
                  aria-label="Rotate left"
                  title="Rotate 90° counter-clockwise"
                >
                  <RotateCcw className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setRotation((r) => (r + 90) % 360)}
                  aria-label="Rotate right"
                  title="Rotate 90° clockwise"
                >
                  <RotateCw className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="w-12 t-eyebrow" style={{ fontSize: 11 }}>
                Zoom
              </span>
              <input
                type="range"
                min={1}
                max={4}
                step={0.05}
                value={zoom}
                onChange={(e) => setZoom(Number(e.target.value))}
                className="flex-1"
                style={{ accentColor: "var(--green)" }}
              />
              <span className="w-12 text-right num t-small">
                {zoom.toFixed(1)}×
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
              >
                Replace image…
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={onPickFile}
              />
              {error && (
                <p className="ml-2 t-small" style={{ color: "var(--danger)" }}>{error}</p>
              )}
              <div className="ml-auto flex gap-2">
                <Button variant="ghost" onClick={onClose}>
                  Cancel
                </Button>
                <Button onClick={onSaveClick} disabled={saving || !croppedPixels}>
                  {saving ? "Saving…" : "Save"}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}

// Renders the source image into an offscreen canvas with the requested
// rotation, then extracts the crop rectangle as a JPEG Blob — upscaled to
// MIN_LONG_SIDE so display containers never need to upscale further.
async function getCroppedImg(
  src: string,
  pixelCrop: Area,
  rotation: number
): Promise<Blob> {
  const image = await loadImage(src);
  const radians = (rotation * Math.PI) / 180;

  const sin = Math.abs(Math.sin(radians));
  const cos = Math.abs(Math.cos(radians));
  const bboxW = image.width * cos + image.height * sin;
  const bboxH = image.width * sin + image.height * cos;

  const stage = document.createElement("canvas");
  stage.width = bboxW;
  stage.height = bboxH;
  const sctx = stage.getContext("2d");
  if (!sctx) throw new Error("Canvas 2D context unavailable.");
  sctx.imageSmoothingEnabled = true;
  sctx.imageSmoothingQuality = "high";
  sctx.translate(bboxW / 2, bboxH / 2);
  sctx.rotate(radians);
  sctx.drawImage(image, -image.width / 2, -image.height / 2);

  const longSide = Math.max(pixelCrop.width, pixelCrop.height);
  const scale = longSide < MIN_LONG_SIDE ? MIN_LONG_SIDE / longSide : 1;
  const outW = Math.round(pixelCrop.width * scale);
  const outH = Math.round(pixelCrop.height * scale);

  const out = document.createElement("canvas");
  out.width = outW;
  out.height = outH;
  const octx = out.getContext("2d", { alpha: false });
  if (!octx) throw new Error("Canvas 2D context unavailable.");
  octx.imageSmoothingEnabled = true;
  octx.imageSmoothingQuality = "high";
  octx.drawImage(
    stage,
    pixelCrop.x,
    pixelCrop.y,
    pixelCrop.width,
    pixelCrop.height,
    0,
    0,
    outW,
    outH
  );

  return new Promise<Blob>((resolve, reject) => {
    out.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("toBlob failed"))),
      "image/jpeg",
      0.95
    );
  });
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = (e) => reject(e);
    img.src = src;
  });
}

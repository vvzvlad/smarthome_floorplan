// Pure logic for the button widget, shared by the read-only preview in
// EntityOverlay.vue (editor) and the interactive button in
// InteractiveFloorplan.vue (viewer). Extracted so the caption fallback can be
// unit-tested once and stay consistent between both components.

/**
 * Resolve the caption a button widget should display: the configured `text`
 * when non-empty (after trimming), otherwise the `fallback` (the entity label).
 */
export function formatButtonLabel(text: string | undefined, fallback: string): string {
  const t = (text ?? '').trim();
  return t !== '' ? t : fallback;
}

# Collector Operations visual system

This operates inside the existing Collector identity: system sans typography, restrained indigo accents, neutral surfaces, thin borders, and compact controls. Product clarity and daily operational use govern the composition.

Design tokens live in `frontend/src/styles/tokens.css`. Use 14px body text, 13px data, 12px metadata, 16px section titles, 20px page titles, and 24px metrics. Meaningful secondary text uses the muted color; the subtle token is reserved for decoration. Spacing follows 4/8/12/16/24/32/40px. Controls use 6px radii, panels 8px, dialogs 10px. Shadows belong to overlays. Lucide icons use 16px/18px and consistent stroke weight.

Pages use a 224px sidebar, a compact top bar, and one page header with context actions. Investigation records are tables on desktop and compact lists on phones. Investigation creation uses five validated steps. Reports is a review queue linking to investigation details. Field Agents keeps accounts, shifts, and assigned work visibly separate.

Route Planning uses a 304px investigation and agent roster, a flexible Leaflet map, and a 344px route inspector at wide desktop sizes. At 1200–1439px, route details move into a drawer. Tablets use mutually exclusive drawers; phones use Records, Map, and Routes tabs. Map data always has a list equivalent. Full-person markers indicate configured shift starting points; investigation pins are distinct. Only persisted assignments and validated published road routes appear as assigned, and H3 is labeled as density only.

Controls need visible focus, explicit labels, non-color-only status text, specific errors, and meaningful loading and empty states. Dialogs preserve focus. Mobile controls are at least 44px. Motion is short and functional; recurring menus do not animate and reduced motion is respected.

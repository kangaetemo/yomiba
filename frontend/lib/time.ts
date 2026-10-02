/**
 * Server timestamps -> Turkish wall-clock time.
 *
 * The API stores UTC. Values read back from SQLite arrive without a zone
 * ("2026-10-03T09:13:00"), which JavaScript would read as LOCAL time; and
 * pages rendered on the server format in the server's zone (UTC). Both
 * showed times three hours behind, so every timestamp goes through here.
 */

/** The site's audience and stores are in Turkey. */
export const TIME_ZONE = "Europe/Istanbul";

const HAS_ZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

/** Parse an API timestamp; a zone-less one is UTC. */
export function serverDate(iso: string): Date {
  return new Date(HAS_ZONE.test(iso) ? iso : `${iso}Z`);
}

const DATE_TIME = new Intl.DateTimeFormat("tr-TR", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: TIME_ZONE,
});

/** "3 Eki 12:13" in Turkish time. */
export function formatDateTime(iso: string | null | undefined): string {
  return iso ? DATE_TIME.format(serverDate(iso)) : "—";
}

/**
 * Human label for a volume number.
 *
 * `0` is a real volume (e.g. "Jujutsu Kaisen 0"). Only `null` — or a
 * negative legacy sentinel, should one ever reach the client — means the
 * number is unknown.
 */
export function volumeLabel(number: number | null | undefined): string {
  if (number === null || number === undefined || number < 0) {
    return "Cilt numarası belirsiz";
  }
  return `Cilt ${number}`;
}

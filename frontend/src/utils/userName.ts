export function formatUserName(name: string): string {
  return name
    .trim()
    .split(/\s+/u)
    .filter(Boolean)
    .map((word) => word.charAt(0).toLocaleUpperCase() + word.slice(1).toLocaleLowerCase())
    .join(" ");
}

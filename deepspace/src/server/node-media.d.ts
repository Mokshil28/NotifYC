/** Local demo media reads. The worker enables nodejs_compat; these declarations stay narrow. */
declare module 'node:fs' {
  export function existsSync(path: string): boolean
  export function statSync(path: string): { size: number }
  export function readFileSync(path: string): Uint8Array
}

declare module 'node:path' {
  export function join(...parts: string[]): string
}

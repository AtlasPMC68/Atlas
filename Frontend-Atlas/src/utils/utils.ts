// ---------- helpers ----------
type IsTuple<T> = T extends readonly any[]
  ? number extends T["length"]
    ? false
    : true
  : false;

// ---------- snake-case string transform ----------
type SnakeCase<S extends string> = S extends `${infer Head}${infer Tail}`
  ? Tail extends Uncapitalize<Tail>
    ? `${Lowercase<Head>}${SnakeCase<Tail>}`
    : `${Lowercase<Head>}_${SnakeCase<Uncapitalize<Tail>>}`
  : S;

// ---------- main recursive mapper ----------
type SnakeArray<T> = Array<Snake<T>>;

export type Snake<T> =
  // don't transform functions / builtins
  T extends Function | Date | RegExp | Map<any, any> | Set<any>
    ? T
    : // tuples: map element-wise
      IsTuple<T> extends true
      ? { [K in keyof T]: Snake<T[K]> }
      : // arrays
        T extends Array<infer U>
        ? SnakeArray<U>
        : // objects: but if there's an index signature (string extends keyof T) leave as-is
          T extends object
          ? string extends keyof T
            ? T
            : {
                [K in keyof T as K extends string ? SnakeCase<K> : K]: Snake<
                  T[K]
                >;
              }
          : T;

export function snakeToCamel<T>(obj: Snake<T> | null): T {
  if (Array.isArray(obj)) {
    return obj.map((v) => snakeToCamel(v)) as unknown as T;
  } else if (obj !== null && typeof obj === "object") {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([key, val]) => [
        key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()),
        snakeToCamel(val),
      ]),
    ) as unknown as T;
  }
  return obj as unknown as T;
}

export function camelToSnake(obj: unknown): unknown {
  if (Array.isArray(obj)) {
    return obj.map((v) => camelToSnake(v));
  } else if (obj !== null && typeof obj === "object") {
    return Object.fromEntries(
      Object.entries(obj).map(([key, val]) => [
        key.replace(/([A-Z])/g, "_$1").toLowerCase(),
        camelToSnake(val),
      ]),
    );
  }
  return obj;
}

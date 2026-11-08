/** Compatibility accessors: KriyoPay is the only active product. */
export function partnerKey(): string { return ""; }
export function partnerHeaders(): Record<string,string> { return {}; }
export const authStorage = {
  getItem: (key:string) => localStorage.getItem(key),
  setItem: (key:string,value:string) => localStorage.setItem(key,value),
  removeItem: (key:string) => localStorage.removeItem(key),
};
export const authSessionStorage = {
  getItem: (key:string) => sessionStorage.getItem(key),
  setItem: (key:string,value:string) => sessionStorage.setItem(key,value),
  removeItem: (key:string) => sessionStorage.removeItem(key),
};

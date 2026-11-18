// Browser geolocation (works on https and localhost). The customer is asked
// for permission by the browser the first time.

export type Coords = { lat: number; lng: number };

export function getPosition(): Promise<Coords> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) return reject({ code: -1 });
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: +p.coords.latitude.toFixed(6), lng: +p.coords.longitude.toFixed(6) }),
      (e) => reject(e),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    );
  });
}

export function geoErrorText(e: unknown): string {
  const code = (e as { code?: number })?.code;
  if (code === 1) return "إذن الموقع مقفول. فعّله من إعدادات المتصفح أو اكتب العنوان";
  return "مقدرناش نحدد موقعك، اكتب العنوان بدل كده";
}

export function mapsPin(lat: number, lng: number): string {
  return `https://www.google.com/maps?q=${lat},${lng}`;
}

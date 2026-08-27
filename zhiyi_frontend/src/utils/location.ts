/**
 * 浏览器实时定位工具。
 *
 * 通过 Geolocation API 获取用户当前真实位置，把经纬度映射到支持的
 * 配送城市（长沙/上海），生成可在物流接口中直接解析的收货地址
 * （带 LOC:lng,lat 前缀，后端会解析为精确终点坐标）。
 *
 * 定位失败 / 被拒绝 / 不在支持城市内时返回 null，由调用方回落到默认地址。
 */

export interface LocatedInfo {
  /** 城市名，如 “长沙” */
  city: string
  /** 界面展示文案，如 “长沙 · 实时定位” */
  label: string
  /** 可直接提交的收货地址文本 */
  address: string
  lng: number
  lat: number
}

/** 城市判定范围：[lngMin, lngMax, latMin, latMax]，与后端 CITY_RANGES 保持一致 */
const CITY_RANGES: Record<string, [number, number, number, number]> = {
  changsha: [112.8, 113.3, 28.05, 28.45],
  shanghai: [120.98, 121.88, 30.9, 31.45],
}

const CITY_NAMES: Record<string, string> = { changsha: '长沙', shanghai: '上海' }

function cityFromCoords(lng: number, lat: number): string | null {
  for (const [city, [lngMin, lngMax, latMin, latMax]] of Object.entries(CITY_RANGES)) {
    if (lng >= lngMin && lng <= lngMax && lat >= latMin && lat <= latMax) return city
  }
  return null
}

function getCurrentPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject(new Error('浏览器不支持定位'))
      return
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 8000,
      maximumAge: 60_000,
    })
  })
}

/** 获取当前真实位置；失败时返回 null。 */
export async function locateCurrentCity(): Promise<LocatedInfo | null> {
  try {
    const pos = await getCurrentPosition()
    const lng = Number(pos.coords.longitude.toFixed(6))
    const lat = Number(pos.coords.latitude.toFixed(6))
    const cityKey = cityFromCoords(lng, lat)
    if (!cityKey) return null
    const city = CITY_NAMES[cityKey]
    return {
      city,
      label: `${city} · 实时定位`,
      address: `LOC:${lng},${lat} 湖南省${city}市（当前位置）`,
      lng,
      lat,
    }
  } catch {
    return null
  }
}

/** 默认收货地址（定位失败时使用）。 */
export function defaultDeliveryAddress(): string {
  return import.meta.env.VITE_DEFAULT_DELIVERY_ADDRESS || '湖南省长沙市岳麓区梅溪湖路888号'
}

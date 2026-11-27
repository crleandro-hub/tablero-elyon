/* ═══════════════════════════
   precio_cba_cache.js  -  Grupo Elyon
   Generado por update_precio_cba_cache.py el 27/11/2026 11:04
   Precio de OFERTA de departamentos en venta en Cordoba capital,
   en dolares por m2. Es precio PEDIDO, no escriturado.
   Roomix: serie mensual propia (CSV) + valor de departamentos.
   Mudafy: monitor diario, sirve de control cruzado.
   NO editar a mano: se pisa en cada corrida.
═══════════════════════════ */
window.PRECIO_CBA_CACHE = {
  chequeado: "2026-11-27T11:04:29",
  aviso: null,
  updated: "2026-11-27T11:04:29",
  source: "Roomix + Mudafy · precio de oferta",
  roomix: {
    nombre: "Roomix",
    mes: "2026-11",
    mesSerie: "2026-10",
    deptosUsdM2: 1633,
    deptosAvisos: 5287,
    totalUsdM2: 1309,
    varIa: 8.5,
    url: "https://roomix.ai/roomix-index/cordoba-capital",
    serie: [["2025-08",1071],["2025-09",1076],["2025-10",1206],["2025-11",1233],["2025-12",1217],["2026-01",1218],["2026-02",1224],["2026-03",1230],["2026-04",1230],["2026-05",1256],["2026-06",1238],["2026-07",1250],["2026-08",1277],["2026-09",1291],["2026-10",1309]],
    serieDeptos: [["2026-11",1633]],
    barrios: [["Valle Escondido",2556],["Villa Belgrano",1966],["Nueva Córdoba",1950],["General Paz",1714],["Güemes",1400],["Cofico",1364],["El Viejo Algarrobo",1278],["Manantiales",1222],["Centro",1209],["Alto Alberdi",1200],["Argüello",1186],["Alberdi",1161],["Observatorio",1125],["Alta Córdoba",1043],["General Pueyrredón",977],["Nobu Town",972],["Altos de General Paz",923],["San Martín",889],["Docta",878],["Juniors",873],["Las Palmas",841],["Siete Soles Naturaleza Urbana",768],["San Salvador",741],["Villa Warcalde",717]]
  },
  mudafy: {
    nombre: "Mudafy",
    mes: "2026-11",
    fecha: "27/11/2026",
    deptosUsdM2: 1501,
    tipico: null,
    url: "https://mudafy.com.ar/monitor-inmobiliario/cordoba-cordoba-capital",
    serieDeptos: [["2026-11",1501]]
  }
};

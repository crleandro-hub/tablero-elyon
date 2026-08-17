/* ═══════════════════════════════════════════════════════════════════
   salarios_cache.js  ·  Grupo Elyon
   ═══════════════════════════════════════════════════════════════════
   Escalas salariales de los dos convenios de la construccion.
   NO se genera por script: las paritarias salen en PDF y no hay API
   confiable, asi que este archivo SE EDITA A MANO cuando se homologa
   un acuerdo nuevo (2 a 4 veces por anio). Es a proposito: es la unica
   forma de que el dato sea correcto.

   COMO AGREGAR UN MES NUEVO (UOCRA)
   ---------------------------------
   1. Buscar la escala homologada (jorgevega.com.ar / camarco.org.ar).
   2. Tomar la columna "Basico" = Zona A, que es la que aplica a Cordoba.
   3. Agregar una fila AL FINAL de uocra.serie, respetando el orden:
        ["aaaa-mm", oficialEspecializado, oficial, medioOficial, ayudante]
   4. Actualizar el campo "actualizado" de mas abajo.

   OJO CON LOS SALTOS
   ------------------
   Varios meses muestran subas del basico muy superiores al porcentaje
   pactado (ej. ago-2026 +9,1 con un acuerdo de +1,9). No es un error:
   son las SUMAS NO REMUNERATIVAS que se incorporan al basico. Por eso
   la variacion del basico NO equivale al aumento real de bolsillo.
   Los porcentajes de acuerdo se cargan en uocra.pactado (mas abajo) y el
   tablero los usa para mostrar el aumento real al lado del nominal.
═══════════════════════════════════════════════════════════════════ */

window.SALARIOS_CACHE = {
  actualizado: "2026-08-07",

  uocra: {
    nombre:  "UOCRA",
    cct:     "CCT 76/75 y 577/10",
    zona:    "Zona A (incluye Cordoba)",
    unidad:  "hora",
    fuente:  "Escalas homologadas - jorgevega.com.ar",
    /* Zona A: CABA, Bs. As., Sgo. del Estero, Santa Fe, Mendoza, San Juan,
       Catamarca, CORDOBA, Entre Rios, Salta, Tucuman, Chaco, San Luis,
       Corrientes, La Rioja, Formosa, Jujuy y Misiones. */
    categorias: [
      ["oficialEsp",   "Oficial especializado"],
      ["oficial",      "Oficial"],
      ["medioOficial", "Medio oficial"],
      ["ayudante",     "Ayudante"]
    ],
    /* PORCENTAJES REALMENTE PACTADOS EN LA PARITARIA
       -----------------------------------------------
       El basico salta muy por encima del acuerdo en los meses en que se
       INCORPORA al basico una suma no remunerativa que el trabajador ya venia
       cobrando aparte. Ese salto no es aumento de bolsillo: solo cambia de
       donde sale la plata. Ejemplo: ago-2026 muestra +9,1% de basico con un
       acuerdo de +1,9%.

       Aca va, mes por mes, el porcentaje que fija el acuerdo homologado. El
       tablero arma con esto una serie homogenea y lee el poder de compra sin
       el ruido de las incorporaciones. Los meses que no esten listados usan la
       variacion del basico tal cual.

       AL CARGAR UN ACUERDO NUEVO, agregar aca sus porcentajes.

       Fuente: acuerdos homologados CCT 76/75 (UOCRA - CAMARCO/FAEC)
         mar-2026  2,0 %                          jun-2026  2,1 %  (absorbe la SNR de mayo)
         abr-2026  1,9 %  (absorbe parte de SNR)  jul-2026  2,0 %
         may-2026  1,8 %                          ago-2026  1,9 %  (absorbe la SNR de julio) */
    pactado: {
      "2026-03": 2.0, "2026-04": 1.9, "2026-05": 1.8,
      "2026-06": 2.1, "2026-07": 2.0, "2026-08": 1.9
    },

    /* ["aaaa-mm", oficialEsp, oficial, medioOficial, ayudante]  -  $/hora */
    serie: [
      ["2022-05", 463, 394, 364, 334],
      ["2022-06", 505, 430, 397, 364],
      ["2022-08", 539, 459, 423, 388],
      ["2022-09", 593, 506, 466, 428],
      ["2022-10", 648, 552, 509, 467],
      ["2022-11", 699, 595, 549, 504],
      ["2022-12", 732, 624, 575, 528],
      ["2023-01", 787, 670, 618, 568],
      ["2023-02", 842, 717, 661, 607],
      ["2023-03", 863, 735, 678, 622],
      ["2023-04", 949, 809, 745, 684],
      ["2023-05", 1018, 867, 800, 734],
      ["2023-06", 1052, 897, 827, 759],
      ["2023-07", 1158, 986, 909, 835],
      ["2023-08", 1262, 1075, 991, 910],
      ["2023-09", 1363, 1161, 1071, 983],
      ["2023-10", 1526, 1301, 1199, 1101],
      ["2023-11", 1694, 1444, 1331, 1222],
      ["2023-12", 1881, 1602, 1477, 1356],
      ["2024-01", 2257, 1923, 1773, 1628],
      ["2024-02", 2573, 2192, 2021, 1855],
      ["2024-04", 2933, 2499, 2304, 2115],
      ["2024-05", 3255, 2774, 2558, 2348],
      ["2024-06", 3613, 3079, 2839, 2606],
      ["2024-08", 3794, 3233, 2981, 2736],
      ["2024-09", 3946, 3362, 3100, 2846],
      ["2024-10", 4104, 3497, 3224, 2960],
      ["2024-11", 4268, 3637, 3353, 3078],
      ["2024-12", 4439, 3782, 3487, 3201],
      ["2025-01", 4519, 3850, 3550, 3259],
      ["2025-02", 4694, 4015, 3711, 3415],
      ["2025-03", 4741, 4056, 3748, 3450],
      ["2025-05", 4846, 4145, 3831, 3526],
      ["2025-06", 4894, 4187, 3869, 3561],
      ["2025-07", 4948, 4233, 3912, 3600],
      ["2025-08", 5002, 4279, 3955, 3640],
      ["2025-09", 5067, 4335, 4006, 3687],
      ["2025-10", 5128, 4387, 4054, 3731],
      ["2025-11", 5200, 4449, 4111, 3784],
      ["2025-12", 5268, 4506, 4164, 3833],
      ["2026-01", 5373, 4596, 4248, 3910],
      ["2026-02", 5470, 4679, 4324, 3980],
      ["2026-03", 5579, 4773, 4411, 4060],
      ["2026-04", 6011, 5142, 4752, 4374],
      ["2026-05", 6119, 5235, 4837, 4452],
      ["2026-06", 6666, 5703, 5270, 4851],
      ["2026-07", 6800, 5817, 5375, 4948],
      ["2026-08", 7420, 6348, 5866, 5399]
    ]
  },

  uecara: {
    nombre:  "UECARA",
    cct:     "CCT 660/13",
    zona:    "Zona II (Centro) - escala nacional",
    unidad:  "mes",
    fuente:  "Acuerdo CAMARCO/FAEC-UECARA jun-jul-ago 2026",
    /* IMPORTANTE PARA ELYON: el CCT 660/13 rige en TODO EL PAIS EXCEPTO
       CORDOBA. En Cordoba se aplica el CCT 735/15 (UECARA Cordoba), que
       sigue los mismos porcentajes de paritaria pero tiene basicos
       propios y no se publica online. Los valores de abajo sirven como
       referencia nacional; para la escala de Cordoba hay que cargar los
       basicos de las liquidaciones propias en uecaraCba.serie. */
    categorias: [
      ["capataz1",  "Capataz de obra"],
      ["capataz2",  "Capataz de tarea/fase"],
      ["capataz3",  "Capataz de segunda"],
      ["adm1",      "Analista administrativo"],
      ["adm2",      "Auxiliar administrativo"],
      ["adm3",      "Ayudante administrativo"],
      ["adm4",      "Ayudante administrativo 2da"],
      ["tec1",      "Analista tecnico"],
      ["tec2",      "Auxiliar tecnico"],
      ["tec3",      "Ayudante tecnico"],
      ["tec4",      "Ayudante tecnico 2da"],
      ["sis1",      "Analista de sistemas"],
      ["sis2",      "Tecnico de sistemas 1ra"],
      ["sis3",      "Tecnico de sistemas 2da"],
      ["maest1",    "Maestranza 1ra"],
      ["maest2",    "Maestranza 2da"]
    ],
    /* ["aaaa-mm", {categoria: basico mensual}, esEstimado] */
    serie: [
      ["2026-06", { capataz1:1967304, capataz2:1795070, capataz3:1644633,
                    adm1:1549010, adm2:1432787, adm3:1311153, adm4:1151535,
                    tec1:1694007, tec2:1572469, tec3:1447358, tec4:1282797,
                    sis1:1694484, sis2:1572945, sis3:1283274,
                    maest1:916960, maest2:813965 }, false],
      /* Julio: el acuerdo fija +2 por ciento liso sobre los basicos de junio. */
      ["2026-07", { capataz1:2006650, capataz2:1830971, capataz3:1677526,
                    adm1:1579990, adm2:1461443, adm3:1337376, adm4:1174566,
                    tec1:1727887, tec2:1603918, tec3:1476305, tec4:1308453,
                    sis1:1728374, sis2:1604404, sis3:1308939,
                    maest1:935299, maest2:830244 }, true]
      /* Agosto 2026: +1,9 por ciento MAS absorcion de la suma no
         remunerativa de julio. Como el monto absorbido no esta publicado,
         no se carga: cargalo desde la escala homologada. */
    ]
  },

  /* Escala propia de Cordoba (CCT 735/15). Vacia a proposito: cargala
     desde tus liquidaciones con el mismo formato que uecara.serie. */
  uecaraCba: {
    nombre:  "UECARA Cordoba",
    cct:     "CCT 735/15",
    zona:    "Provincia de Cordoba",
    unidad:  "mes",
    fuente:  "A cargar desde liquidaciones propias",
    categorias: [],
    serie: []
  }
};

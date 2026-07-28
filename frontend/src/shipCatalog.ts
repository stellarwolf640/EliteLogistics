export interface CoreSizes {
  powerPlant: number;
  thrusters: number;
  frameShiftDrive: number;
  lifeSupport: number;
  powerDistributor: number;
  sensors: number;
  fuelTank: number;
}

export interface ShipTemplate {
  model: string;
  pad: "S" | "M" | "L";
  stockCargo: number;
  cargoBuild: number;
  balancedRange: number;
  cargoRange: number;
  role: string;
  core: CoreSizes;
  optionalSlots: number[];
  utilities: number;
  hardpoints: string[];
}

const ship = (
  model: string,
  pad: "S" | "M" | "L",
  stockCargo: number,
  cargoBuild: number,
  balancedRange: number,
  cargoRange: number,
  role: string,
  core: number[],
  optionalSlots: number[],
  utilities: number,
  hardpoints: string[],
): ShipTemplate => ({
  model, pad, stockCargo, cargoBuild, balancedRange, cargoRange, role,
  core: {
    powerPlant: core[0], thrusters: core[1], frameShiftDrive: core[2],
    lifeSupport: core[3], powerDistributor: core[4], sensors: core[5], fuelTank: core[6],
  },
  optionalSlots, utilities, hardpoints,
});

export const SHIP_CATALOG: ShipTemplate[] = [
  ship("Sidewinder Mk I", "S", 4, 10, 15, 11, "Starter courier", [2, 2, 2, 1, 1, 1, 2], [2, 2, 1], 2, ["2× Small"]),
  ship("Hauler", "S", 8, 26, 24, 17, "Light transport", [2, 2, 2, 1, 1, 1, 2], [3, 3, 2, 1], 2, ["1× Small"]),
  ship("Adder", "S", 6, 30, 22, 16, "Light multipurpose", [3, 3, 3, 1, 2, 2, 3], [3, 3, 2, 2, 1], 2, ["1× Medium", "2× Small"]),
  ship("Cobra Mk III", "S", 18, 64, 24, 18, "Fast multipurpose", [4, 4, 4, 3, 3, 3, 4], [4, 4, 4, 2, 2, 2], 2, ["2× Medium", "2× Small"]),
  ship("Type-6 Transporter", "M", 50, 114, 24.7, 18.7, "Medium freighter", [3, 4, 4, 2, 3, 2, 4], [5, 5, 4, 4, 3, 2, 2, 1], 3, ["2× Small"]),
  ship("Keelback", "M", 38, 96, 22, 16, "Defended freighter", [4, 4, 4, 3, 3, 3, 4], [5, 5, 4, 3, 3, 2, 2], 3, ["2× Medium", "2× Small"]),
  ship("Type-7 Transporter", "L", 128, 306, 22, 15, "Large freighter", [4, 5, 5, 3, 4, 3, 5], [6, 6, 6, 5, 5, 4, 3, 2, 1], 4, ["4× Small"]),
  ship("Type-8 Transporter", "M", 176, 406, 26, 18, "Heavy medium-pad freighter", [5, 5, 5, 3, 4, 3, 5], [7, 6, 6, 6, 5, 5, 4, 3, 2, 1], 4, ["2× Medium", "5× Small"]),
  ship("Python", "M", 82, 294, 23, 16, "Armed medium trader", [7, 6, 5, 4, 7, 6, 5], [6, 6, 6, 5, 5, 5, 4, 3, 3, 2, 1], 4, ["3× Large", "2× Medium"]),
  ship("Krait Mk II", "M", 82, 230, 25, 18, "Fast armed trader", [7, 6, 5, 4, 7, 6, 5], [6, 6, 6, 5, 5, 4, 3, 3, 2, 1], 4, ["3× Large", "2× Medium"]),
  ship("Type-9 Heavy", "L", 220, 790, 18, 12, "Bulk freighter", [6, 7, 6, 5, 6, 4, 6], [8, 8, 8, 7, 6, 5, 4, 3, 2, 1], 4, ["3× Large", "2× Medium"]),
  ship("Imperial Cutter", "L", 164, 794, 24, 17, "Fast shielded bulk trader", [8, 8, 7, 7, 7, 7, 6], [8, 8, 8, 6, 6, 6, 5, 5, 4, 3, 1], 8, ["1× Huge", "2× Large", "4× Medium"]),
  ship("Panther Clipper Mk II", "L", 384, 1238, 20, 13, "Maximum-volume logistics", [8, 8, 7, 5, 7, 5, 7], [8, 8, 8, 8, 7, 7, 6, 6, 5, 4, 3, 2, 1], 6, ["2× Large", "4× Medium"]),
];

export type OptimizationMode = "Cargo first" | "Range first" | "Safety first" | "Balanced";

export interface ModuleChoice {
  slot: string;
  module: string;
  purpose: string;
}

function coreModules(ship: ShipTemplate, mode: OptimizationMode): ModuleChoice[] {
  const safety = mode === "Safety first";
  const lightweight = mode === "Cargo first" || mode === "Range first";
  const powerSize = lightweight ? Math.max(2, ship.core.powerPlant - 1) : ship.core.powerPlant;
  const distributorSize = lightweight ? Math.max(1, ship.core.powerDistributor - 1) : ship.core.powerDistributor;
  return [
    { slot: "Bulkheads", module: safety ? "Military Grade Composite" : "Lightweight Alloy", purpose: safety ? "Maximum hull protection" : "Preserve range and cargo performance" },
    { slot: `Class ${ship.core.powerPlant}`, module: `${powerSize}A Power Plant`, purpose: lightweight ? "Downsized efficient power" : "Full-output power reserve" },
    { slot: `Class ${ship.core.thrusters}`, module: `${ship.core.thrusters}${safety ? "A" : "D"} Thrusters`, purpose: safety ? "Escape speed and control" : "Lower mass" },
    { slot: `Class ${ship.core.frameShiftDrive}`, module: `${ship.core.frameShiftDrive}A Frame Shift Drive`, purpose: "Maximum practical jump performance" },
    { slot: `Class ${ship.core.lifeSupport}`, module: `${ship.core.lifeSupport}D Life Support`, purpose: "Lowest mass" },
    { slot: `Class ${ship.core.powerDistributor}`, module: `${distributorSize}${safety ? "A" : "D"} Power Distributor`, purpose: safety ? "Repeated boosting under pressure" : "Enough output for normal hauling" },
    { slot: `Class ${ship.core.sensors}`, module: `${ship.core.sensors}D Sensors`, purpose: "Lowest mass" },
    { slot: `Class ${ship.core.fuelTank}`, module: `${ship.core.fuelTank}C Fuel Tank`, purpose: "Standard integrated fuel capacity" },
  ];
}

function optionalModules(ship: ShipTemplate, mode: OptimizationMode): ModuleChoice[] {
  let scoopUsed = false;
  let boosterUsed = false;
  let shieldUsed = false;
  let assistUsed = false;
  let reinforcementCount = 0;
  const minShield = ship.pad === "L" ? 5 : ship.pad === "M" ? 3 : 2;
  return ship.optionalSlots.map((size, index) => {
    if (mode === "Range first" && !scoopUsed) {
      scoopUsed = true;
      return { slot: `Optional ${index + 1} · Class ${size}`, module: `${size}A Fuel Scoop`, purpose: "Minimize refuelling stops" };
    }
    if (mode === "Range first" && !boosterUsed && size >= 5) {
      boosterUsed = true;
      return { slot: `Optional ${index + 1} · Class ${size}`, module: "5H Guardian FSD Booster", purpose: "Extend every laden jump" };
    }
    if ((mode === "Safety first" || mode === "Balanced") && !shieldUsed && size >= minShield) {
      shieldUsed = true;
      const shieldClass = Math.min(size, mode === "Safety first" ? minShield + 1 : minShield);
      return { slot: `Optional ${index + 1} · Class ${size}`, module: `${shieldClass}${mode === "Safety first" ? "A" : "D"} Shield Generator`, purpose: mode === "Safety first" ? "Primary collision and interdiction protection" : "Docking protection without excessive cargo loss" };
    }
    if (mode === "Safety first" && reinforcementCount < 2 && size >= 3) {
      reinforcementCount += 1;
      return { slot: `Optional ${index + 1} · Class ${size}`, module: `${size}D ${reinforcementCount === 1 ? "Hull" : "Module"} Reinforcement Package`, purpose: "Survive failed escapes" };
    }
    if (mode === "Balanced" && !scoopUsed && size >= 4) {
      scoopUsed = true;
      return { slot: `Optional ${index + 1} · Class ${size}`, module: `${size}A Fuel Scoop`, purpose: "Support relocation and longer routes" };
    }
    if (!assistUsed && size === 1) {
      assistUsed = true;
      return { slot: `Optional ${index + 1} · Class ${size}`, module: "1E Advanced Docking Computer", purpose: "Routine logistics convenience" };
    }
    return { slot: `Optional ${index + 1} · Class ${size}`, module: `${size}E Cargo Rack`, purpose: `Carry ${2 ** size} t of cargo` };
  });
}

function utilityModules(ship: ShipTemplate, mode: OptimizationMode): ModuleChoice[] {
  const safety = mode === "Safety first";
  return Array.from({ length: ship.utilities }, (_, index) => {
    const modules = safety
      ? ["A-Rated Shield Booster", "Heat Sink Launcher", "Chaff Launcher", "Point Defence"]
      : ["Heat Sink Launcher", "Chaff Launcher", "Point Defence", "Empty"];
    const module = modules[index % modules.length];
    return { slot: `Utility ${index + 1}`, module, purpose: module === "Empty" ? "Preserve mass and power" : "Defensive escape support" };
  });
}

export function optimizeShip(ship: ShipTemplate, mode: OptimizationMode) {
  const headline = mode === "Cargo first"
    ? { cargo: ship.cargoBuild, ladenRange: ship.cargoRange, shields: "None / optional", scoop: "None" }
    : mode === "Range first"
      ? { cargo: Math.max(ship.stockCargo, Math.round(ship.cargoBuild * 0.58)), ladenRange: Math.round(ship.balancedRange * 1.22 * 10) / 10, shields: "None", scoop: "Largest slot" }
      : mode === "Safety first"
        ? { cargo: Math.max(ship.stockCargo, Math.round(ship.cargoBuild * 0.62)), ladenRange: ship.balancedRange, shields: "Strong A-rated", scoop: "Optional" }
        : { cargo: Math.max(ship.stockCargo, Math.round(ship.cargoBuild * 0.78)), ladenRange: ship.balancedRange, shields: "Light D-rated", scoop: "Standard" };
  return {
    ...headline,
    note: mode === "Cargo first" ? "Maximum racks and minimum support equipment." : mode === "Range first" ? "Fuel scoop and Guardian booster take priority over hold space." : mode === "Safety first" ? "Shields, reinforcement, utilities, and boost performance protect the load." : "A practical shielded trader with a scoop and strong remaining capacity.",
    core: coreModules(ship, mode),
    optional: optionalModules(ship, mode),
    utilities: utilityModules(ship, mode),
    hardpoints: ship.hardpoints.map((slot, index) => ({ slot: `Hardpoint group ${index + 1}`, module: mode === "Safety first" ? `${slot} lightweight defensive weapons` : `${slot} empty`, purpose: mode === "Safety first" ? "Discourage light attackers while escaping" : "Avoid combat mass; submit, boost, and jump" })),
  };
}

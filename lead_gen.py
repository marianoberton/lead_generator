"""Orquestador principal de generación de leads para FOMO."""

import argparse
import sys
import traceback

from dotenv import load_dotenv

load_dotenv()

STEPS = {
    1: ("Apollo API", "src.step1_apollo"),
    2: ("Google Places", "src.step2_google"),
    3: ("Web Crawling", "src.step3_crawl"),
    4: ("Personalización", "src.step4_personalize"),
    5: ("CSV Listmonk", "src.step5_csv"),
    6: ("Reporte", "src.step6_report"),
    7: ("Dashboard", "src.step7_dashboard"),
}


def run_step(step_num: int) -> bool:
    """Ejecuta un paso individual. Retorna True si fue exitoso."""
    if step_num not in STEPS:
        print(f"ERROR: Paso {step_num} no existe. Pasos válidos: 1-7")
        return False

    name, module_path = STEPS[step_num]
    print(f"\n{'='*60}")
    print(f"  PASO {step_num}: {name}")
    print(f"{'='*60}")

    try:
        module = __import__(module_path, fromlist=["run"])
        module.run()
        print(f"\n[OK] Paso {step_num} ({name}) completado.")
        return True
    except Exception as e:
        print(f"\n[FAIL] Paso {step_num} ({name}) fallo: {e}")
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="FOMO Lead Generation Pipeline")
    parser.add_argument(
        "--step", type=int, default=None,
        help="Ejecutar solo un paso (1-7)",
    )
    args = parser.parse_args()

    print("FOMO Lead Generation Pipeline")
    print("=" * 60)

    if args.step is not None:
        success = run_step(args.step)
        sys.exit(0 if success else 1)

    # Ejecutar todos los pasos
    failed = []
    for step_num in sorted(STEPS.keys()):
        success = run_step(step_num)
        if not success:
            failed.append(step_num)
            # Pasos 1-3 son críticos, si fallan no seguir
            if step_num <= 3:
                print(f"\nERROR: Paso {step_num} es crítico. Abortando pipeline.")
                sys.exit(1)

    print(f"\n{'='*60}")
    print("  PIPELINE COMPLETADO")
    print(f"{'='*60}")
    if failed:
        print(f"  Pasos con errores: {failed}")
    else:
        print("  Todos los pasos ejecutados correctamente.")
    print()


if __name__ == "__main__":
    main()

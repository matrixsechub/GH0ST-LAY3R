"""
Ghost Layer Studio — Demo Runner

This script boots the full Ghost Layer engine and runs a sample input.
"""

from core.engine import create_default_engine


def banner():
    print("\n" + "=" * 72)
    print("        GHOST LAYER STUDIO — ENGINE DEMO")
    print("=" * 72 + "\n")


def pretty_print(result):
    import json
    print(json.dumps(result, indent=4))


def main():
    banner()

    engine = create_default_engine()

    sample_input = "Boot sequence: Ghost Layer Studio online."
    print(f"[DEMO] Input: {sample_input}\n")

    result = engine.run(sample_input, source="demo-script")

    print("[DEMO] Output:\n")
    pretty_print(result)


if __name__ == "__main__":
    main()

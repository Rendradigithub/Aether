import re

old_init = """        if weights_path.exists():
            self.decoder.load_weights(weights_path)
            self.bootstrapping_phase = False
            if not self.quiet:
                print("[Bootstrapping] Skipped (weights found)")
        else:
            if not self.quiet:
                print(f"[Bootstrapping] Phase active for {self.bootstrapping_end_cycle} cycles")"""

new_init = """        if weights_path.exists():
            success = self.decoder.load_weights(weights_path)
            if success:
                self.bootstrapping_phase = False
                if not self.quiet:
                    print("[Bootstrapping] Skipped (weights found)")
            else:
                if not self.quiet:
                    print(f"[Bootstrapping] Phase active for {self.bootstrapping_end_cycle} cycles")
        else:
            if not self.quiet:
                print(f"[Bootstrapping] Phase active for {self.bootstrapping_end_cycle} cycles")"""

for filename in ["src/aether/orchestrator.py", "archive/versions/aether.0.20.0.py"]:
    with open(filename, "r") as f:
        content = f.read()
    if old_init in content:
        content = content.replace(old_init, new_init)
        with open(filename, "w") as f:
            f.write(content)
        print(f"Patched {filename}")
    else:
        print(f"Not found in {filename}")

"""Image-owned launcher. No user directories are on the import path."""
import sys

sys.path.insert(0, "/opt/proofflow")

from verifier.entrypoint import main

sys.exit(main())

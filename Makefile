.PHONY: test demo ask scale diagrams clean
test:      ; python -m pytest -q
demo:      ; python -m drone_analyst simulate && python -m drone_analyst run
ask:       ; python -m drone_analyst chat
scale:     ; python scripts/scalability_test.py --frames 50000 --db output/scale.db --json docs/scalability_results.json
diagrams:  ; cd docs && for f in architecture pipeline data_model; do dot -Tpng -Gdpi=150 $$f.dot -o $$f.png; done
clean:     ; rm -f output/*.db

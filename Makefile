# Although building locally, we need a full image path, otherwise kpt assumes a gcr.io registry
IMAGE=registry.hub.docker.com/michaelvl/helm2yaml-local

.PHONY: build
build:
	docker build -t $(IMAGE) .

.PHONY: clean-rendered
clean-rendered:
	rm -rf rendered && mkdir rendered

.PHONY: test1
test1: clean-rendered
	(cd examples && cat krm-input.yaml | ../helm2yaml.py -l DEBUG --render-path ../rendered krm -f -)

.PHONY: test1-stdout
test1-stdout: clean-rendered
	(cd examples && cat krm-input.yaml | ../helm2yaml.py -l DEBUG -o stdout krm -f - 1> ../function-out.yaml 2> ../stderr.txt)

.PHONY: test2
test2: clean-rendered
	(cd rendered && kpt fn eval --image $(IMAGE) --truncate-output=false --network --as-current-user --fn-config ../examples/fn-config.yaml --mount type=bind,src=`pwd`"/../examples/",dst=/source -o unwrap)

.PHONY: test3
test3: clean-rendered
	(cd examples && cat krm-kube-prometheus-stack.yaml | ../helm2yaml.py -l DEBUG --skip-helm --render-path ../rendered krm --export-upgraded-krm exported.yaml -f -)

.PHONY: test3-1
test3-1: clean-rendered
	(cd examples && cat krm-kube-prometheus-stack.yaml | ../helm2yaml.py -l DEBUG --render-path ../rendered krm -f -)

service_name = patient-svc

.PHONY: start
start:
	docker-compose up -d

.PHONY: clean
clean:
	docker-compose down
	docker rmi -f $(service_name)

.PHONY: test
test:
	docker exec -it $(service_name) sh -c pytest

.PHONY: logs
logs:
	docker logs -f $(service_name)

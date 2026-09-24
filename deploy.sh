#!/bin/bash

set -euo pipefail

# Define colors as variables
GREEN="\033[1;32m"
CYAN="\033[1;36m"
RED="\033[1;31m"
YELLOW="\033[1;33m"
BLUE="\033[1;34m"
MAGENTA="\033[1;35m"
BOLD="\033[1m"
UNDERLINE="\033[4m"
# Define no color
NC="\033[0m" # No Color

fetch_latest_changes(){
    target_branch="${1:-main}"

    echo -e "${CYAN}${BOLD}Configuring git user...${NC}"
    git config user.email "deploy@deploy.com"
    git config user.name "deploy"

    echo -e "${GREEN}${BOLD}Fetching latest code for branch ${UNDERLINE}$target_branch${NC}"
    git fetch origin "$target_branch"

    if git show-ref --verify --quiet "refs/heads/$target_branch"; then
        git checkout "$target_branch"
        git pull --ff-only origin "$target_branch"
    else
        git checkout -b "$target_branch" "origin/$target_branch"
    fi
}

deploy_ci(){
    target_branch="${1:-main}"
    project_name=$(basename "$(git rev-parse --show-toplevel)" | tr '[:upper:]' '[:lower:]')

    compose_file="${COMPOSE_FILE:-docker-compose.prod.yml}"
    echo -e "${CYAN}${BOLD}Using compose file: ${UNDERLINE}$compose_file${NC}"

    echo -e "${YELLOW}${BOLD}Stop existing services on compose project ${UNDERLINE}$project_name"_"$target_branch${NC}"
    docker compose --project-name "$project_name"_"$target_branch" -f "$compose_file" down --remove-orphans

    echo -e "${BLUE}${BOLD}Cleaning cache build for older than 10 days for ${UNDERLINE}$target_branch${NC}"
    docker builder prune -f --filter until=240h
    docker buildx prune -f --filter until=240h
    docker image prune -a -f

    echo -e "${MAGENTA}${BOLD}Rebuilding services for ${UNDERLINE}$project_name"_"$target_branch${NC} ${MAGENTA}${BOLD} using branch ${UNDERLINE}$target_branch${NC}"
    docker compose --project-name "$project_name"_"$target_branch" -f "$compose_file" up --build -d

    # Verify containers are healthy
    echo -e "${CYAN}${BOLD}Verifying container health...${NC}"
    project_prefix="${project_name}_$target_branch"
    max_attempts=30
    sleep_interval=5

    for attempt in $(seq 1 $max_attempts); do
        echo -e "${CYAN}Health check attempt $attempt/$max_attempts${NC}"

        # Get all containers for this project
        containers=$(docker compose --project-name "$project_prefix" -f "$compose_file" ps -q 2>/dev/null)

        if [ -z "$containers" ]; then
            echo -e "${RED}${BOLD}No containers found for project $project_prefix${NC}"
            exit 1
        fi

        all_healthy=true
        failed_container=""

        for container_id in $containers; do
            container_name=$(docker inspect --format '{{.Name}}' "$container_id" | sed 's/^\///')
            container_status=$(docker inspect --format '{{.State.Status}}' "$container_id")

            if [ "$container_status" = "exited" ] || [ "$container_status" = "dead" ]; then
                all_healthy=false
                failed_container=$container_name
                echo -e "${RED}${BOLD}Container $container_name has status: $container_status${NC}"
                break
            elif [ "$container_status" != "running" ]; then
                all_healthy=false
                echo -e "${YELLOW}Container $container_name is $container_status, waiting...${NC}"
            fi
        done

        # If a container failed, show logs and exit
        if [ -n "$failed_container" ]; then
            echo -e "${RED}${BOLD}Container $failed_container failed to start. Logs:${NC}"
            docker logs "$failed_container" --tail 100
            exit 1
        fi

        if [ "$all_healthy" = true ]; then
            echo -e "${GREEN}${BOLD}All containers are running${NC}"
            break
        fi

        if [ $attempt -eq $max_attempts ]; then
            echo -e "${RED}${BOLD}Containers failed to become healthy after $max_attempts attempts${NC}"
            docker compose --project-name "$project_prefix" -f "$compose_file" ps
            exit 1
        fi

        sleep $sleep_interval
    done

    echo -e "${GREEN}${BOLD}✓ Deployment complete!${NC}"
}

"$@"

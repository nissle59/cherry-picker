RELEASE_VER="1.2.1"
SOURCE_BRANCH="test"
TARGET_BRANCH="pre-prod"

REPOS=(
  "../eco-backend/"
  "../eco-auth/"
  "../eco-notifications/"
  "../airflow/"
  "../rpn-handler/"
)

for REPO in "${REPOS[@]}"; do
    if [ -d "$REPO" ]; then
        echo "Обработка репозитория: $REPO"
        python3 git_cherry_picker.py "$SOURCE_BRANCH" "$TARGET_BRANCH" tasks.txt --release="$RELEASE_VER" --repo-dir="$REPO"
        echo "----------------------------------------"
    else
        echo "ВНИМАНИЕ: Директория $REPO не существует, пропускаем"
    fi
done
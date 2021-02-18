

# dev_repository_root = "C:/Users/davidlatwe.lai/pipeline/rez-kit"
dev_repository_root = "C:/Users/davidlatwe.lai/pipeline/rez-deliver/test"

rez_source_path = "C:/Users/davidlatwe.lai/pipeline/rez"

deliver_targets = [
    # name: target name
    # template: package install/release path template
    # source: JSON that contains key-values for template keyword formatting
    {
        "name": "dept",
        "description": "department beta",
        "template": "T:/rez-studio/packages/1/beta-dept/{department}",
        "source": "T:/rez-studio/deploy/data/targets.json",
    },
    {
        "name": "user",
        "description": "user beta",
        "template": "T:/rez-studio/packages/1/beta-user/{user}",
        "source": "T:/rez-studio/deploy/data/targets.json",
    },
]

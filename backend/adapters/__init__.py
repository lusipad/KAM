from adapters.azure_devops import AzureDevOpsAdapter
from adapters.ci import CIAdapter
from adapters.github import GitHubPRAdapter

ADAPTERS = {
    "github_pr": GitHubPRAdapter,
    "azure_devops": AzureDevOpsAdapter,
    "ci_pipeline": CIAdapter,
}

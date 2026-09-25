---
schema_version: knowledge.v1
kind: guidance
title: Test observable behavior
description: Test the changed behavior and its failure boundaries without duplicating implementation details.
scope: [org:example]
topics: [testing]
languages: [any]
technologies: [any]
environments: [any]
---

# Test observable behavior

For changed filtering behavior, cover isolation, ordering, pagination and an
empty result where relevant to the feature contract.

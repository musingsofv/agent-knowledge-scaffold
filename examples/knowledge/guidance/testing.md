---
schema_version: knowledge.v1
kind: guidance
title: Test observable behavior
description: Test changed behavior and its failure boundaries without duplicating implementation details.
scope: [org:example]
topics: [testing]
languages: [any]
technologies: [any]
environments: [any]
---

# Test observable behavior

## Applies when

Adding or changing filtering behavior. Select checks from the actual feature
contract; a wording-only documentation edit does not require new behavior tests.

## Review checks

- [ ] When filtering controls visibility, verify that excluded records are not
  returned through the public boundary.
- [ ] When ordering or pagination is part of the changed contract, verify the
  promised order and page boundaries with representative records.
- [ ] When no records match, verify the documented empty response.

## Rationale

Public behavior is the contract. Tests tied only to private implementation
details can pass even when that contract breaks.

## Verification

Use focused public-boundary test results for the final changed state. Existing
tests can supply evidence when they cover that state; do not add duplicate tests
to satisfy a checkbox. Passing these tests does not establish deployed behavior.

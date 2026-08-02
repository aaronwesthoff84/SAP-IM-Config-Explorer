# XML Compatibility Matrix

SAP IM Config Explorer loads only the local SAP Incentive Management XML bytes supplied by the user. Loading does not call an external service or transmit XML content.

## Supported profiles

The supported document profile has an exact `DATA_IMPORT` root local name. A root namespace is optional. Namespace-qualified element and attribute names are normalized to their local names before extractor matching and XML-path generation. The namespace URI itself does not authorize an object type: an unknown local name remains unknown and cannot bypass the strict graph node allowlist.

An export version is recorded only when the root has an explicit, case-sensitive `VERSION` attribute, including a namespace-qualified `VERSION` attribute. Missing versions are reported as `null`; they are not inferred.

## Supported encodings

| Normalized value | Accepted evidence | Regression coverage |
| --- | --- | --- |
| `utf-8` | UTF-8 bytes, an optional UTF-8 BOM, and an optional `UTF-8` declaration | `base_profile.xml`, path and upload matrix |
| `utf-16-le` | UTF-16 little-endian BOM or little-endian XML declaration byte signature; declaration may be `UTF-16` or an LE alias | Bytes derived from `base_profile.xml` in the path and upload matrix |
| `utf-16-be` | UTF-16 big-endian BOM or big-endian XML declaration byte signature; declaration may be `UTF-16` or a BE alias | Bytes derived from `base_profile.xml` in the path and upload matrix |

Decoding is strict. Unsupported declarations, declaration/BOM mismatches, and malformed byte sequences fail without replacement characters. Errors include the affected filename and a safe encoding reason.

## Sanitized fixture profiles

| Fixture | Namespace evidence | Version evidence | Verified shape |
| --- | --- | --- | --- |
| `tests/fixtures/compatibility/base_profile.xml` | None | Root `VERSION="16.0"` | Plan, Plan Component, Rule, and their containment references |
| `tests/fixtures/compatibility/namespace_profile.xml` | `urn:sap:incentive-management:configuration:16.0` | Namespace-qualified root `VERSION="16.0"` | Same canonical graph plus a namespace-qualified unknown element that remains excluded |

`tests/test_xml_compatibility.py` verifies both file-path loading and in-memory upload loading. The UTF-8, UTF-8 BOM, UTF-16 LE, UTF-16 BE, and namespace-qualified variants must produce the same literal canonical nodes, links, XML paths, and findings.

## Exported compatibility evidence

Graph schema `1.1` adds `sourceProfiles` to every serialized snapshot. Entries preserve input order and contain:

- `sourceFile`
- `encoding`
- `namespaceUri`, or `null`
- `exportVersion`, or `null`

The decoded source text remains available on the loaded `XmlDocument` as `raw_text`; normalization changes the parsed element names used by extractors, not that source evidence.

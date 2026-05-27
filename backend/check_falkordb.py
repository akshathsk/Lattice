import falkordb

print("Connecting to FalkorDB at localhost:6379 ...")

try:
    db = falkordb.FalkorDB(host="localhost", port=6379)

    # drop test graph if it exists from a previous run
    g = db.select_graph("lattice_test")
    try:
        g.delete()
    except Exception:
        pass
    g = db.select_graph("lattice_test")
    result = g.query("RETURN 'FalkorDB connected!' AS msg")
    print("✓", result.result_set[0][0])

    # create a node and read it back
    g.query("CREATE (:TestNode {name: 'hello', value: 42})")
    result = g.query("MATCH (n:TestNode) RETURN n.name, n.value")
    name, value = result.result_set[0]
    print(f"✓ Node round-trip OK — name={name}, value={value}")

    # check vector index support
    g.query("""
        CREATE VECTOR INDEX FOR (c:Chunk) ON (c.embedding)
        OPTIONS {dimension: 4, similarityFunction: 'cosine'}
    """)
    print("✓ Vector index created")

    # write a node with a vector embedding
    g.query("CREATE (:Chunk {text: 'test chunk', embedding: vecf32([0.1, 0.2, 0.3, 0.4])})")

    # query the vector index
    result = g.query("""
        CALL db.idx.vector.queryNodes('Chunk', 'embedding', 1, vecf32([0.1, 0.2, 0.3, 0.4]))
        YIELD node, score
        RETURN node.text, score
    """)
    text, score = result.result_set[0]
    print(f"✓ Vector KNN search OK — chunk='{text}', distance={score:.4f}")

    # clean up
    g.delete()
    print("\n✓ All checks passed — FalkorDB is ready")

except Exception as e:
    print(f"✗ Connection failed: {e}")

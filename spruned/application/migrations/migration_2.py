import binascii


def migrate(sql):
    action = """
    CREATE TABLE headers_temp (
        id INTEGER PRIMARY KEY ASC,
        blockheight INTEGER,
        blockhash BLOB NOT NULL,
        data BLOB NOT NULL
    )
    """
    sql.execute(action)
    sql.flush()
    sql.execute("CREATE UNIQUE INDEX blockhash_index ON headers(blockhash);")
    sql.flush()
    sql.execute("CREATE UNIQUE INDEX blockheight_index ON headers(blockheight);")
    sql.flush()
    offset = 0
    while 1:
        action = "SELECT * FROM headers where id > %s limit %s" % (offset, 10000)
        res = sql.execute(action).fetchall()
        if not res:
            break
        data = [
            {
                'blockheight': entry['blockheight'],
                'blockhash': binascii.unhexlify(entry['blockhash']),
                'data': entry['data']
            } for entry in res
        ]
        query = """
            INSERT INTO headers_temp (blockheight, blockhash, data) 
            VALUES 
            (:blockheight, :blockhash, :data)
            """
        sql.execute(query, data)
        sql.commit()
        offset += 10000
    sql.execute("DROP TABLE headers")
    sql.execute("ALTER TABLE headers_temp RENAME TO headers;")
    sql.execute("UPDATE migrations SET version = 2")
    sql.commit()
    sql.execute("VACUUM")
    sql.close()
    return True

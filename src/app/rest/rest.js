
const express = require('express')
const app = express()
const port = 8080
const oracledb = require('oracledb');

app.get('/info', (req, res) => {
    res.send('NodeJS - Express - Oracle')
})

app.get('/dept', async (req, res) => {
    let con = await oracledb.getConnection({ user: process.env.DB_USER, password: process.env.DB_PASSWORD, connectionString: process.env.DB_URL });
    result = await con.execute(
        `select deptno, dname, loc from DEPT`,
        [],
        { resultSet: true, outFormat: oracledb.OUT_FORMAT_OBJECT });
    const rs = result.resultSet;
    let row;
    let rows = [];
    while ((row = await rs.getRow())) {
        rows.push(row);
    }
    await rs.close();
    await con.close();
    res.send(rows)
})

app.listen(port, () => {
    console.log(`OCI Starter: listening on port ${port}`)
})